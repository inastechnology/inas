const MAX_SYNC_BODY_BYTES = 1024 * 1024;

export class RequestBodyError extends Error {
  constructor(
    message: string,
    readonly status = 400,
  ) {
    super(message);
    this.name = "RequestBodyError";
  }
}

export async function readSyncJson(request: Request): Promise<unknown> {
  const mediaType = request.headers.get("Content-Type")?.split(";", 1)[0].trim().toLowerCase();
  if (mediaType !== "application/json") {
    throw new RequestBodyError("Content-Type must be application/json", 415);
  }
  const contentLength = request.headers.get("Content-Length");
  if (contentLength) {
    const parsed = Number(contentLength);
    if (!Number.isSafeInteger(parsed) || parsed < 0) {
      throw new RequestBodyError("Content-Length is invalid");
    }
    if (parsed > MAX_SYNC_BODY_BYTES) {
      throw new RequestBodyError("request body exceeds 1 MiB", 413);
    }
  }
  if (!request.body) {
    throw new RequestBodyError("request body is required");
  }
  const contentEncoding = request.headers.get("Content-Encoding")?.trim().toLowerCase() ?? "";
  const encodedBytes = await readBounded(request.body, MAX_SYNC_BODY_BYTES);
  let bytes = encodedBytes;
  if (contentEncoding === "gzip") {
    const decompressor = new DecompressionStream("gzip") as unknown as TransformStream<Uint8Array, Uint8Array>;
    const encodedStream = new Blob([asArrayBuffer(encodedBytes)]).stream();
    bytes = await readBounded(encodedStream.pipeThrough(decompressor), MAX_SYNC_BODY_BYTES);
  } else if (contentEncoding && contentEncoding !== "identity") {
    throw new RequestBodyError("Content-Encoding is not supported", 415);
  }
  let text: string;
  try {
    text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch {
    throw new RequestBodyError("request body is not valid UTF-8");
  }
  try {
    return JSON.parse(text);
  } catch {
    throw new RequestBodyError("request body is not valid JSON");
  }
}

async function readBounded(stream: ReadableStream<Uint8Array>, limit: number): Promise<Uint8Array> {
  const reader = stream.getReader();
  const chunks: Uint8Array[] = [];
  let length = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      length += value.byteLength;
      if (length > limit) {
        await reader.cancel("body too large");
        throw new RequestBodyError("request body exceeds 1 MiB", 413);
      }
      chunks.push(value);
    }
  } catch (error) {
    if (error instanceof RequestBodyError) {
      throw error;
    }
    throw new RequestBodyError("request body could not be decoded");
  } finally {
    reader.releaseLock();
  }
  const result = new Uint8Array(length);
  let offset = 0;
  for (const chunk of chunks) {
    result.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return result;
}

function asArrayBuffer(bytes: Uint8Array): ArrayBuffer {
  const copy = new Uint8Array(bytes.byteLength);
  copy.set(bytes);
  return copy.buffer;
}
