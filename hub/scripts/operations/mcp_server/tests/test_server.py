import base64
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.shared.memory import create_connected_server_and_client_session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import create_server  # noqa: E402


class McpServerTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = Mock()
        self.client.list_fields.return_value = {"items": [{"id": "field-a"}], "has_more": False, "next_cursor": None}
        self.client.search_records.return_value = {"items": [{"id": "note-a", "title": "葉の色", "attachments": [{"id": "photo-a"}]}]}
        self.client.camera_image.return_value = (b"\xff\xd8\xffframe", "image/jpeg")
        self.client.record_image.return_value = (b"\x89PNG\r\n\x1a\nleaf", "image/png")
        self.server = create_server(self.client)

    async def test_initialize_discover_read_tools_and_query_records(self):
        async with create_connected_server_and_client_session(self.server) as session:
            tools = (await session.list_tools()).tools
            self.assertEqual(
                {tool.name for tool in tools}, {"list_fields", "search_records", "list_cameras", "list_camera_images", "get_camera_image", "get_record_image"}
            )
            self.assertTrue(all(tool.annotations.readOnlyHint for tool in tools))
            result = await session.call_tool("search_records", {"field_id": "field-a", "query": "葉", "source": "note"})
            self.assertFalse(result.isError)
            self.assertIn("葉の色", json.dumps(result.model_dump(), ensure_ascii=False))
        self.client.search_records.assert_called_once_with("field-a", query="葉", source="note", date_from="", date_to="", since="", cursor="", limit=50)

    async def test_tools_return_real_image_content(self):
        async with create_connected_server_and_client_session(self.server) as session:
            result = await session.call_tool("get_record_image", {"field_id": "field-a", "attachment_id": "photo-a"})
            self.assertFalse(result.isError)
            self.assertEqual(result.content[0].type, "image")
            self.assertEqual(result.content[0].mimeType, "image/png")
            self.assertEqual(base64.b64decode(result.content[0].data), self.client.record_image.return_value[0])
            result = await session.call_tool("get_camera_image", {"field_id": "field-a", "camera_id": "camera-a", "image_id": "20260923_090000"})
            self.assertEqual(result.content[0].mimeType, "image/jpeg")

    async def test_api_denial_is_an_mcp_tool_error(self):
        self.client.list_fields.side_effect = RuntimeError("Operations API returned HTTP 403")
        async with create_connected_server_and_client_session(self.server) as session:
            result = await session.call_tool("list_fields", {})
            self.assertTrue(result.isError)
            self.assertIn("403", result.content[0].text)

    async def test_stdio_entrypoint_initialize_and_discover_without_hub_access(self):
        parameters = StdioServerParameters(
            command=sys.executable,
            args=[str(Path(__file__).resolve().parents[1] / "server.py"), "--env-file", "/nonexistent/inas-collector-test.env"],
            env={"CF_ACCESS_CLIENT_ID": "test", "CF_ACCESS_CLIENT_SECRET": "test", "INAS_HUB_OPERATIONS_URL": "https://example.invalid/operations/api/v1"},
        )
        async with stdio_client(parameters) as (read, write), ClientSession(read, write) as session:
            initialized = await session.initialize()
            self.assertEqual(initialized.serverInfo.name, "INA Hub read-only collection")
            self.assertEqual(len((await session.list_tools()).tools), 6)


if __name__ == "__main__":
    unittest.main()
