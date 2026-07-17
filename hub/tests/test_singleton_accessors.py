import ast
import unittest
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "src" / "ina_device_hub"


def _called_class_name(call: ast.Call, class_names: set[str]):
    if isinstance(call.func, ast.Name):
        return call.func.id if call.func.id in class_names else None
    if isinstance(call.func, ast.Attribute):
        return call.func.attr if call.func.attr in class_names else None
    return None


def _uses_module_singleton(function: ast.FunctionDef):
    return any(isinstance(node, ast.Global) and "__instance" in node.names for node in function.body)


def _uses_singleton_cache(function: ast.FunctionDef):
    for decorator in function.decorator_list:
        if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Name) or decorator.func.id != "lru_cache":
            continue
        if any(keyword.arg == "maxsize" and isinstance(keyword.value, ast.Constant) and keyword.value.value == 1 for keyword in decorator.keywords):
            return True
    return False


def _singleton_constructors(trees: dict[Path, ast.Module]):
    class_names = {node.name for tree in trees.values() for node in tree.body if isinstance(node, ast.ClassDef)}
    constructors = {}
    for path, tree in trees.items():
        for function in (node for node in tree.body if isinstance(node, ast.FunctionDef)):
            if not (_uses_module_singleton(function) or _uses_singleton_cache(function)):
                continue
            for node in ast.walk(function):
                if isinstance(node, ast.Call) and (class_name := _called_class_name(node, class_names)):
                    constructors.setdefault(class_name, set()).add((path, function.name))
    return constructors


class _DirectConstructorVisitor(ast.NodeVisitor):
    def __init__(self, path: Path, constructors: dict[str, set[tuple[Path, str]]]):
        self.path = path
        self.constructors = constructors
        self.function_names = []
        self.violations = []
        self.aliases = {}

    def visit_ImportFrom(self, node):  # noqa: N802
        for imported in node.names:
            if imported.name in self.constructors:
                self.aliases[imported.asname or imported.name] = imported.name

    def visit_FunctionDef(self, node):  # noqa: N802
        self.function_names.append(node.name)
        self.generic_visit(node)
        self.function_names.pop()

    def visit_AsyncFunctionDef(self, node):  # noqa: N802
        self.visit_FunctionDef(node)

    def visit_Call(self, node):  # noqa: N802
        class_name = None
        if isinstance(node.func, ast.Name):
            class_name = self.aliases.get(node.func.id, node.func.id)
        elif isinstance(node.func, ast.Attribute):
            class_name = node.func.attr

        if class_name in self.constructors:
            current_function = self.function_names[-1] if self.function_names else ""
            if (self.path, current_function) not in self.constructors[class_name]:
                self.violations.append(f"{self.path.name}:{node.lineno}: use the singleton accessor instead of {class_name}()")
        self.generic_visit(node)


class SingletonAccessorTest(unittest.TestCase):
    def test_singleton_classes_are_only_constructed_by_their_accessors(self):
        trees = {path: ast.parse(path.read_text(encoding="utf-8"), filename=str(path)) for path in PACKAGE_ROOT.glob("*.py")}
        constructors = _singleton_constructors(trees)
        violations = []

        for path, tree in trees.items():
            visitor = _DirectConstructorVisitor(path, constructors)
            visitor.visit(tree)
            violations.extend(visitor.violations)

        self.assertEqual(violations, [], "\n".join(violations))


if __name__ == "__main__":
    unittest.main()
