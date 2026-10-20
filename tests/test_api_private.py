"""pywebview exposes every public attribute of the js_api object to JavaScript and (6.x) walks
them recursively to list functions. On Windows that walk entered Api.bar.window.native (the
WinForms form) and froze the app. So Api keeps all its state in underscore attributes."""
import ast
import os
import unittest

APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py")


class ApiStateIsPrivate(unittest.TestCase):
    def test_every_self_attribute_assigned_in_api_is_private(self):
        tree = ast.parse(open(APP, encoding="utf-8").read())
        api = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Api")
        public = sorted({n.attr for n in ast.walk(api)
                         if isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Store)
                         and isinstance(n.value, ast.Name) and n.value.id == "self"
                         and not n.attr.startswith("_")})
        self.assertEqual(public, [], "pywebview would expose these to JS and walk into them")


if __name__ == "__main__":
    unittest.main()
