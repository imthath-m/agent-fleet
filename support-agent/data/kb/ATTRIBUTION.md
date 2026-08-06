# Attribution

The knowledge base ingested by `triage/ingest.py` into
`data/kb/ubuntu_docs.jsonl` is sourced from the
[Ubuntu Community Help Wiki](https://help.ubuntu.com/community/)
(`help.ubuntu.com/community/`), maintained by the Ubuntu community.

The wiki's content is licensed under the
[Creative Commons Attribution-ShareAlike 4.0 International License](https://creativecommons.org/licenses/by-sa/4.0/)
(**CC BY-SA 4.0**), per https://help.ubuntu.com/community/License.

Every ingested chunk carries this attribution in its `Document.metadata`:

```json
{
  "license": "CC BY-SA 4.0",
  "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
  "title": "<wiki page title>",
  "url": "<wiki page URL>"
}
```

**Obligation:** any surface that displays KB text derived from this corpus
(resolver answers, the review CLI, the landing-page trial in Phase 7) must
also display the source page's URL and the CC BY-SA 4.0 license — see
task 7.3.
