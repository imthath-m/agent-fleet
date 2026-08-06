from triage import config
from triage.kb import attribution_for, check_grounding, load_kb

# --------------------------------------------------------------------------- #
# load_kb() / query
# --------------------------------------------------------------------------- #


def test_load_kb_is_queryable():
    retriever = load_kb()
    passages = retriever.query(config.KB_NAMESPACE, "how do I add a user to a group", top_k=4)

    assert len(passages) >= 1
    assert retriever.get(config.KB_NAMESPACE, passages[0].doc_id) is not None


# --------------------------------------------------------------------------- #
# 10 hand-written probe queries (Phase 1 exit criterion: >= 8/10 relevant).
# Each maps to one or more doc_id prefixes that count as a relevant hit --
# multiple pages can genuinely answer the same support question.
# --------------------------------------------------------------------------- #

PROBE_QUERIES: list[tuple[str, tuple[str, ...]]] = [
    ("usermod add user to group command line", ("AddUsersHowto",)),
    ("how do I create a bootable USB installer", ("Installation/FromUSBStick",)),
    ("how do I install ubuntu alongside windows", ("Installation",)),
    ("how do I enable the firewall", ("Firewall", "Gufw", "DoINeedAFirewall")),
    ("how do I connect to a wifi network", ("WifiDocs",)),
    ("how do I add a software repository ppa", ("PPA", "Repositories")),
    ("cups print server configure printer", ("Printers",)),
    ("forgot ubuntu password recovery mode reset", ("LostPassword",)),
    ("change file permissions with chmod command", ("FilePermissions",)),
    (
        "how do I fix a broken package installation",
        (
            "AptGet",
            "SynapticHowto",
            "PackageManagerTroubleshootingProcedure",
            "AptitudeSurvivalGuide",
        ),
    ),
]


def test_probe_queries_hit_rate_is_at_least_8_of_10():
    retriever = load_kb()
    hits = 0
    misses = []
    for query, relevant_prefixes in PROBE_QUERIES:
        passages = retriever.query(config.KB_NAMESPACE, query, top_k=config.RETRIEVAL_TOP_K)
        doc_ids = [p.doc_id for p in passages]
        hit = any(doc_id.startswith(prefix) for doc_id in doc_ids for prefix in relevant_prefixes)
        if hit:
            hits += 1
        else:
            misses.append((query, doc_ids))

    assert hits >= 8, f"only {hits}/10 probe queries hit a relevant chunk; misses: {misses}"


# --------------------------------------------------------------------------- #
# attribution_for()
# --------------------------------------------------------------------------- #


def test_attribution_for_known_doc_carries_license_and_url():
    retriever = load_kb()
    passages = retriever.query(config.KB_NAMESPACE, "sudo", top_k=1)
    assert passages

    attribution = attribution_for(retriever, passages[0].doc_id)
    assert attribution["license"] == "CC BY-SA 4.0"
    assert attribution["url"].startswith("https://help.ubuntu.com/community/")
    assert attribution["title"]


def test_attribution_for_unknown_doc_is_empty():
    retriever = load_kb()
    assert attribution_for(retriever, "not-a-real-doc#0") == {}


# --------------------------------------------------------------------------- #
# check_grounding()
# --------------------------------------------------------------------------- #


def test_fabricated_citation_is_caught():
    retriever = load_kb()
    assert check_grounding(retriever, ["not-a-real-doc#0"]) == ["not-a-real-doc#0"]


def test_real_citation_is_grounded():
    retriever = load_kb()
    passages = retriever.query(config.KB_NAMESPACE, "sudo", top_k=1)
    assert passages
    assert check_grounding(retriever, [passages[0].doc_id]) == []
