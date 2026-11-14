# Error analysis (LIVE run)

**MODE: LIVE**

- model: gpt-6-luna
- judge_model: gpt-6-luna
- run_at: 2026-11-14T12:46:38+00:00
- git_sha: 60dc927
- usage: 168 calls, 84207 in, 35697 out, cost_usd=0.026269

## Scores

| suite | n | metric means | pass rates | errors |
|---|---|---|---|---|
| classification | 18 | schema_pass_rate=1.000, field_accuracy=0.764 | schema_pass_rate=1.000, field_accuracy=0.333 | 0 |
| resolution | 18 | grounding_rate=1.000, llm_judge=0.907, schema_pass_rate=1.000 | grounding_rate=1.000, llm_judge=0.833, schema_pass_rate=1.000 | 0 |
| actions | 15 | tool_call_correctness=0.933, field_accuracy=1.000 | tool_call_correctness=0.933, field_accuracy=1.000 | 0 |
| escalation | 15 | escalation_accuracy=0.933, escalation_precision=0.875, escalation_recall=1.000 | escalation_accuracy=0.933 | 0 |
| triage | 18 | grounding_rate=0.556, schema_pass_rate=1.000 | grounding_rate=0.556, schema_pass_rate=1.000 | 0 |

## classification

12 of 18 examples failed.

Failure patterns:

- 8x sentiment: expected neutral -> got frustrated
- 2x priority: expected high -> got normal
- 2x priority: expected normal -> got high
- 1x intent: expected other -> got complaint
- 1x priority: expected low -> got normal
- 1x intent: expected account -> got technical
- 1x priority: expected high -> got urgent
- 1x intent: expected other -> got how_to

Tags of failing examples: ported (4), urgent (3), billing (2), networking (2), account (1), install (1), packaging (1), users_permissions (1), complaint (1), angry (1), positive (1)

Examples (up to 5):

- `reset-password` tags=['ported', 'account']
  - ticket: I can't log in and the reset email never arrives.
  - expected: {"intent": "account", "priority": "high", "product_area": "users_permissions", "sentiment": "neutral"}
  - predicted: {"text": "{\"intent\": \"account\", \"priority\": \"normal\", \"product_area\": \"users_permissions\", \"sentiment\": \"frustrated\", \"pii_flag\": false}", "fields": {"intent": "account", "priority"…
  - field_accuracy: score=0.500 {"checked": 4, "correct": 2, "mismatches": {"priority": {"expected": "high", "got": "normal"}, "sentiment": {"expected": "neutral", "got": "frustrated"}}}
- `shipping-delay` tags=['ported']
  - ticket: My package was supposed to arrive yesterday but it hasn't.
  - expected: {"intent": "other", "priority": "normal", "product_area": "other", "sentiment": "neutral"}
  - predicted: {"text": "{\"intent\": \"complaint\", \"priority\": \"normal\", \"product_area\": \"other\", \"sentiment\": \"frustrated\", \"pii_flag\": false}", "fields": {"intent": "complaint", "priority": "norma…
  - field_accuracy: score=0.500 {"checked": 4, "correct": 2, "mismatches": {"intent": {"expected": "other", "got": "complaint"}, "sentiment": {"expected": "neutral", "got": "frustrated"}}}
- `cancel-subscription` tags=['ported', 'billing']
  - ticket: Please cancel my subscription, I no longer need it.
  - expected: {"intent": "billing", "priority": "low", "product_area": "other", "sentiment": "neutral"}
  - predicted: {"text": "{\"intent\": \"billing\", \"priority\": \"normal\", \"product_area\": \"other\", \"sentiment\": \"neutral\", \"pii_flag\": false}", "fields": {"intent": "billing", "priority": "normal", "pr…
  - field_accuracy: score=0.750 {"checked": 4, "correct": 3, "mismatches": {"priority": {"expected": "low", "got": "normal"}}}
- `broken-item` tags=['ported']
  - ticket: The item I received is broken and I want a replacement.
  - expected: {"intent": "complaint", "priority": "high", "product_area": "other", "sentiment": "neutral"}
  - predicted: {"text": "{\"intent\": \"complaint\", \"priority\": \"normal\", \"product_area\": \"other\", \"sentiment\": \"frustrated\", \"pii_flag\": false}", "fields": {"intent": "complaint", "priority": "norma…
  - field_accuracy: score=0.500 {"checked": 4, "correct": 2, "mismatches": {"priority": {"expected": "high", "got": "normal"}, "sentiment": {"expected": "neutral", "got": "frustrated"}}}
- `grub-rescue-after-install` tags=['install', 'urgent']
  - ticket: After the installation finished my machine will not boot and GRUB drops to a rescue prompt. Production is down and I cannot work at all.
  - expected: {"intent": "technical", "priority": "urgent", "product_area": "install", "sentiment": "neutral"}
  - predicted: {"text": "{\"intent\": \"technical\", \"priority\": \"urgent\", \"product_area\": \"install\", \"sentiment\": \"frustrated\", \"pii_flag\": false}", "fields": {"intent": "technical", "priority": "urg…
  - field_accuracy: score=0.750 {"checked": 4, "correct": 3, "mismatches": {"sentiment": {"expected": "neutral", "got": "frustrated"}}}

## resolution

3 of 18 examples failed.

Failure patterns:

- 3x judge score 0.3-0.7

Tags of failing examples: users_permissions (1), networking (1), hardware (1)

Examples (up to 5):

- `password-policy` tags=['users_permissions']
  - ticket: What counts as a strong password for the accounts on our Ubuntu machines?
  - expected: {"answer": "A strong password is at least fifteen characters in length, does not contain your user name, real name, organization name or birth date, does not contain a complete dictionary word, is si…
  - predicted: {"text": "For Ubuntu user accounts, a strong password should be **long, unique, and hard to guess**:\n\n- Prefer **at least 15 characters** when the password is the only sign-in factor. A randomly ge…
  - llm_judge: score=0.350 Includes the 15-character minimum and some advice to avoid identifying information, but omits the three-of-four character-type rule and the requirement to differ significantly from the previous password. It also recommends word-based passphrases despite the reference ruling out complete dictionary words.
- `wifi-drops` tags=['networking']
  - ticket: My wireless connection drops every few minutes and I have to reconnect by hand. Where do I start troubleshooting?
  - expected: {"answer": "Recent versions of Ubuntu support most wireless cards. Start from the Wireless Networking Central pages: check the list of supported wireless cards and adapters, then work through getting…
  - predicted: {"text": "Start by checking whether the problem is the Wi‑Fi link or the internet connection:\n\n1. **Check another device on the same Wi‑Fi.** If it also drops, the router or internet service is mor…
  - llm_judge: score=0.500 The troubleshooting steps are generally useful, but the answer misses the expected starting point: Ubuntu’s Wireless Networking Central pages, including checking supported adapters and following the getting-started, connections, and troubleshooting guidance.
- `printer-not-detected` tags=['hardware']
  - ticket: My printer is not detected at all. How do I get it working on Ubuntu?
  - expected: {"answer": "Install and maintain the printer using the tools for its manufacturer - there are pages for HP, Canon, Lexmark, Samsung and Xerox printers. Virtually all of the better models support Post…
  - predicted: {"text": "Try these steps in order. The wireless and printing pages in the supplied documentation refer to old, unsupported Ubuntu releases, so the menu names may differ from yours.\n\n1. **Check the…
  - llm_judge: score=0.650 The answer offers useful connection, Ubuntu, and driver checks, but it misses the expected guidance to use the printer manufacturer’s tools for HP, Canon, Lexmark, Samsung, or Xerox. It mentions manufacturer support generally and HP specifically, but not the other vendor tools.

## actions

1 of 15 examples failed.

Failure patterns:

- 1x missing tool: crm_update

Tags of failing examples: complaint (1), high_risk (1)

Examples (up to 5):

- `install-complaint` tags=['complaint', 'high_risk']
  - ticket: The Ubuntu installer fails every single time and this is ridiculous. I have wasted a whole day on it.
  - expected: {"tool_calls": ["crm_update"], "tool_errors": 0}
  - predicted: {"text": "{\"actions\": [], \"tool_errors\": 0}", "fields": {"actions": [], "tool_errors": 0}}
  - tool_call_correctness: score=0.000 {"expected": ["crm_update"], "got": [], "ordered": false}

## escalation

1 of 15 examples failed.

Failure patterns:

- 1x false positive (needless escalation)

Tags of failing examples: answerable (1), networking (1), hard_negative (1)

Examples (up to 5):

- `wifi-drops` tags=['answerable', 'networking', 'hard_negative']
  - ticket: My wireless connection on Ubuntu drops every few minutes and I have to reconnect manually.
  - expected: {"escalated": false}
  - predicted: {"text": "{\"escalated\": true, \"reason\": \"confidence 0.38 < threshold 0.60; low confidence: retrieval score 0.38\", \"retrieval_score\": 0.38461538461538464}", "fields": {"escalated": true, "reas…
  - escalation_accuracy: score=0.000 {"expected": false, "got": true, "reason": "confidence 0.38 < threshold 0.60; low confidence: retrieval score 0.38", "tp": 7, "fp": 1, "fn": 0, "tn": 7, "escal…

## triage

8 of 18 examples failed.

Failure patterns:

- 8x grounding fail

Tags of failing examples: users_permissions (3), networking (2), hardware (2), packaging (1)

Examples (up to 5):

- `lost-password` tags=['users_permissions']
  - ticket: I have forgotten my Ubuntu login password and cannot get root access to the machine. How do I reset it from recovery mode?
  - expected: {"answer": "Boot into recovery mode to get a full root shell and reset the forgotten password. Be careful: this step gives full root access to your system and you can damage it.", "citations": ["Lost…
  - predicted: {}
  - grounding_rate: score=0.000 {"citations": [], "unresolved": []}
- `directory-permissions` tags=['users_permissions']
  - ticket: What do the read, write and execute permissions actually mean on a directory?
  - expected: {"answer": "On a directory, read restricts or allows viewing the directory contents with the ls command, write restricts or allows creating new files or deleting files in the directory, and execute r…
  - predicted: {}
  - grounding_rate: score=0.000 {"citations": [], "unresolved": []}
- `password-policy` tags=['users_permissions']
  - ticket: What counts as a strong password for the accounts on our Ubuntu machines?
  - expected: {"answer": "A strong password is at least fifteen characters in length, does not contain your user name, real name, organization name or birth date, does not contain a complete dictionary word, is si…
  - predicted: {}
  - grounding_rate: score=0.000 {"citations": [], "unresolved": []}
- `wifi-drops` tags=['networking']
  - ticket: My wireless connection drops every few minutes and I have to reconnect by hand. Where do I start troubleshooting?
  - expected: {"answer": "Recent versions of Ubuntu support most wireless cards. Start from the Wireless Networking Central pages: check the list of supported wireless cards and adapters, then work through getting…
  - predicted: {}
  - grounding_rate: score=0.000 {"citations": [], "unresolved": []}
- `enable-firewall-over-ssh` tags=['networking']
  - ticket: How do I turn on the firewall on an Ubuntu server that I only reach over ssh?
  - expected: {"answer": "Append the ssh rule before you enable the firewall: if you enable the firewall under ssh without the ssh rule you will close the ssh connection. Use the command sudo ufw enable ssh from a…
  - predicted: {}
  - grounding_rate: score=0.000 {"citations": [], "unresolved": []}

