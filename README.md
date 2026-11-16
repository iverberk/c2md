# c2md

Convert a **Confluence Data Center** page to Markdown from the command line. Supports Confluence 7.9+ personal access tokens. The page is exported using the permissions of the token's owner; no administrator account is needed. Cloud API tokens are not supported.

## Install and run

```sh
uv tool install .
c2md 'https://confluence.example.com/pages/viewpage.action?pageId=12345'
```

The first run prompts for your personal access token without displaying it. Create one in Confluence under **avatar → Settings → Personal access tokens → Create token**. For automated use, set `C2MD_TOKEN` in the environment. Do not pass a token on the command line (command lines can appear in process listings and shell history).

To optionally store your token in your OS keyring, install `uv tool install '.[keyring]'` and run with `--save-token`. Without this option, c2md does not store the token. If PATs are disabled by your administrator, ask them to enable them; password and browser-cookie login are not supported.

```sh
c2md 'https://confluence.example.com/display/TEAM/My+Page' -o my-page.md
c2md 12345 --base-url https://confluence.example.com/confluence -o page.md
```

Referenced attachments are downloaded into a folder alongside the Markdown file (for example, `page_assets/`). Existing output is protected unless you pass `--force`. Confluence page links remain links to Confluence. Only files explicitly referenced in the page are downloaded.

Headings, paragraphs, lists, links, images, code, tasks, and simple tables become Markdown. Table-of-contents macros and trailing table-of-contents navigation are omitted. Unsupported macros retain any available text. Multi-column layouts become sequential text; Markdown cannot display columns side by side. Merged table cells and rich table contents may need manual repair. Conversion warnings are counted in the CLI summary, never written into the Markdown. Embedded HTML is never emitted intentionally.

## Develop

```sh
UV_CACHE_DIR=.uv-cache uv sync
UV_CACHE_DIR=.uv-cache uv run python -m unittest discover -s tests -v
```
