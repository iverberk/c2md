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

    def test_unknown_macro_retains_text_without_warning_in_markdown(self):
        storage = '<ac:structured-macro ac:name="custom"><ac:rich-text-body><p>Important text</p></ac:rich-text-body></ac:structured-macro>'
        self.assertEqual(self.converter.convert(storage), "Important text\n")
        self.assertEqual(self.converter.warnings, ["Macro 'custom' may need manual conversion."])

    def test_layout_flattens_without_warning_in_markdown(self):
        storage = '<ac:layout><ac:layout-section><ac:layout-cell><p>Left</p></ac:layout-cell><ac:layout-cell><p>Right</p></ac:layout-cell></ac:layout-section></ac:layout>'
        self.assertEqual(self.converter.convert(storage), "Left\n\nRight\n")
        self.assertEqual(self.converter.warnings, ["Multi-column layout was flattened into reading order."])

    def test_merged_table_and_code(self):
        storage = '<table><tr><th>A</th><th>B</th></tr><tr><td colspan="2">value</td></tr></table><ac:structured-macro ac:name="code"><ac:parameter ac:name="language">python</ac:parameter><ac:plain-text-body><![CDATA[print("hi")]]></ac:plain-text-body></ac:structured-macro>'
        result = self.converter.convert(storage)
        self.assertIn("| A | B |\n| --- | --- |\n| value |  |", result)
        self.assertNotIn("Conversion warning", result)
        self.assertEqual(self.converter.warnings, ["Table has merged cells; verify its columns and rows."])
        self.assertIn('```python\nprint("hi")\n```', result)

    def test_table_links_preserve_targets_and_cell_formatting(self):
        storage = (
            '<table><tr><th><p>Item</p></th><th>Reference</th></tr>'
            '<tr><td><p><ac:link><ri:page ri:content-title="Other Page"/>'
            '<ac:plain-text-link-body>Confluence</ac:plain-text-link-body></ac:link></p></td>'
            '<td><p>See <a href="https://example.com/docs">docs</a> and <strong>notes</strong></p></td></tr>'
            '<tr><td>value | other</td><td><ac:link><ri:attachment ri:filename="pic.png"/>'
            '</ac:link></td></tr></table>'
        )
        self.assertEqual(
            self.converter.convert(storage),
            '| Item | Reference |\n| --- | --- |\n'
            '| [Confluence](https://example.com/DOC/Other%20Page) | See [docs](https://example.com/docs) and **notes** |\n'
            '| value \\| other | [pic.png](assets/pic.png) |\n',
        )
        self.assertEqual(self.converter.warnings, [])

    def test_missing_image_does_not_emit_warning(self):
        result = self.converter.convert('<ac:image><ri:attachment ri:filename="missing.png"/></ac:image>')
        self.assertEqual(result, "missing.png\n")
        self.assertEqual(self.converter.warnings, ["Image attachment 'missing.png' was not available."])

    def test_inline_and_block_warnings_do_not_leak_into_markdown(self):
        storage = ('<p>A <ac:placeholder>draft</ac:placeholder> <custom>text</custom> '
                   '<ac:link><ri:attachment ri:filename="missing.png"/></ac:link></p>'
                   '<script>ignored</script><other><p>Kept</p></other>'
                   '<ac:structured-macro ac:name="note"><ac:rich-text-body><p>Notice</p></ac:rich-text-body></ac:structured-macro>')
        self.assertEqual(self.converter.convert(storage), "A draft text missing.png\n\nKept\n\n**Note:** Notice\n")
        self.assertEqual(len(self.converter.warnings), 6)


if __name__ == "__main__":
    unittest.main()
