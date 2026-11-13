import unittest

from c2md.convert import Converter


class ConversionTests(unittest.TestCase):
    def setUp(self):
        self.converter = Converter(
            "https://example.com/confluence", "DOC", lambda space, title: f"https://example.com/{space}/{title}",
            lambda filename: f"assets/{filename}" if filename != "missing.png" else None,
        )

    def test_common_markdown(self):
        storage = '<h1>Title</h1><p>Hello <strong>world</strong> and <a href="https://example.com">link</a>.</p><ul><li>One<ul><li>Two</li></ul></li></ul>'
        self.assertEqual(self.converter.convert(storage), "# Title\n\nHello **world** and [link](https://example.com).\n\n- One\n  - Two\n")

    def test_confluence_links_images_and_tasks(self):
        storage = (
            '<p><ac:link><ri:page ri:content-title="Other Page"/><ac:plain-text-link-body>read</ac:plain-text-link-body></ac:link></p>'
            '<p><ac:image ac:alt="picture"><ri:attachment ri:filename="pic.png"/></ac:image></p>'
            '<ac:task-list><ac:task><ac:task-status>complete</ac:task-status><ac:task-body>Done</ac:task-body></ac:task></ac:task-list>'
        )
        self.assertEqual(self.converter.convert(storage), "[read](https://example.com/DOC/Other%20Page)\n\n![picture](assets/pic.png)\n\n- [x] Done\n")

    def test_unknown_macro_retains_text_with_warning(self):
        storage = '<ac:structured-macro ac:name="custom"><ac:rich-text-body><p>Important text</p></ac:rich-text-body></ac:structured-macro>'
        self.assertIn("Important text\n\n**Conversion warning:** Macro 'custom' may need manual conversion.", self.converter.convert(storage))

    def test_layout_flattens_with_warning(self):
        storage = '<ac:layout><ac:layout-section><ac:layout-cell><p>Left</p></ac:layout-cell><ac:layout-cell><p>Right</p></ac:layout-cell></ac:layout-section></ac:layout>'
        self.assertEqual(self.converter.convert(storage), "Left\n\nRight\n\n**Conversion warning:** Multi-column layout was flattened into reading order.\n")

    def test_merged_table_and_code(self):
        storage = '<table><tr><th>A</th><th>B</th></tr><tr><td colspan="2">value</td></tr></table><ac:structured-macro ac:name="code"><ac:parameter ac:name="language">python</ac:parameter><ac:plain-text-body><![CDATA[print("hi")]]></ac:plain-text-body></ac:structured-macro>'
        result = self.converter.convert(storage)
        self.assertIn("| A | B |\n| --- | --- |\n| value |  |", result)
        self.assertIn("**Conversion warning:** Table has merged cells", result)
        self.assertIn('```python\nprint("hi")\n```', result)

    def test_missing_image_warns(self):
        result = self.converter.convert('<ac:image><ri:attachment ri:filename="missing.png"/></ac:image>')
        self.assertIn("missing.png **Conversion warning:**", result)


if __name__ == "__main__":
    unittest.main()
