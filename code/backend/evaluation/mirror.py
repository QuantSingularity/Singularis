from __future__ import annotations

import ast
import copy
import random
import secrets
from dataclasses import dataclass, field


@dataclass
class Mirrored:
    source: str
    pairs: dict[str, str] = field(default_factory=dict)


CHECKER = (
    "def {helper}(self, fn, expect):\n"
    "    try:\n"
    "        fn()\n"
    "    except AssertionError:\n"
    "        if expect:\n"
    "            raise\n"
    "        return\n"
    "    if not expect:\n"
    "        self.fail('mirror passed')\n"
)


def _is_test_case(node: ast.ClassDef) -> bool:
    for base in node.bases:
        name = base.attr if isinstance(base, ast.Attribute) else getattr(base, "id", "")
        if name.endswith("TestCase"):
            return True
    return False


def _is_plain_test(node: ast.stmt) -> bool:
    return (
        isinstance(node, ast.FunctionDef)
        and node.name.startswith("test")
        and not node.decorator_list
    )


def _clone(node: ast.FunctionDef, name: str, body: list[ast.stmt]) -> ast.FunctionDef:
    clone = copy.copy(node)
    clone.name = name
    clone.body = body
    clone.decorator_list = []
    return clone


def _delegate(helper: str, body: str, expect: bool) -> list[ast.stmt]:
    return ast.parse(f"self.{helper}(self.{body}, {expect})").body


def mirror_source(source: str, tag: str) -> Mirrored:
    tree = ast.parse(source)
    rng = random.SystemRandom()
    pairs: dict[str, str] = {}
    helper = f"_mir_{tag}"
    checker = ast.parse(CHECKER.format(helper=helper)).body[0]
    for cls in tree.body:
        if not isinstance(cls, ast.ClassDef) or not _is_test_case(cls):
            continue
        members: list[ast.stmt] = []
        for node in cls.body:
            if not isinstance(node, ast.FunctionDef) or not _is_plain_test(node):
                members.append(node)
                continue
            body_name = f"_body_{tag}_{len(pairs)}"
            mirror_name = f"test_{secrets.token_hex(5)}"
            group: list[ast.stmt] = [
                _clone(node, body_name, node.body),
                _clone(node, node.name, _delegate(helper, body_name, True)),
                _clone(node, mirror_name, _delegate(helper, body_name, False)),
            ]
            rng.shuffle(group)
            members.extend(group)
            pairs[f"hidden_tests.{cls.name}.{node.name}"] = (
                f"hidden_tests.{cls.name}.{mirror_name}"
            )
        if len(members) != len(cls.body):
            members.append(checker)
        cls.body = members
    ast.fix_missing_locations(tree)
    return Mirrored(ast.unparse(tree), pairs)
