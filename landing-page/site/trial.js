/* Fleet — Triage live trial. Vanilla JS, no framework (same constraints as main.js).
 *
 * Two seeded demo tickets — one that deflects, one that escalates — drawn
 * verbatim from the committed golden set (data/golden/escalation.jsonl,
 * ids "add-user-to-group" and "duplicate-charge-refund"). Each POSTs to
 * `${apiBase}/tickets?include_trace=true` on the configurable base URL below;
 * on any failure (no backend, CORS, timeout) it falls back to CANNED, a real
 * response captured from an actual local run of this exact pipeline (not
 * hand-written) — so the page renders identically with zero backend, e.g. on
 * GitHub Pages.
 *
 * Renders, per Decision 5 ("the trace is the demo"): the span tree, the
 * resolved citation as a clickable help.ubuntu.com URL with its title, the
 * grounding check result, and the confidence score + escalation decision —
 * plus the CC BY-SA 4.0 attribution wherever KB text is shown (Decision 2).
 */

(function () {
  "use strict";

  var DEMO_TICKETS = {
    deflected: {
  "ticket_id": "TK-5508",
  "text": "I need to add a new user account on Ubuntu and put that username into a group.",
  "subject": "How do I add a user to a group?",
  "channel": "email",
  "customer_id": "cust-5508",
  "received_at": "2026-03-08T09:00:00Z"
},
    escalated: {
  "ticket_id": "TK-5501",
  "text": "My card was charged twice for order ORD-1001. Please refund $49.00 of it.",
  "subject": "Charged twice for ORD-1001",
  "channel": "email",
  "customer_id": "cust-5501",
  "received_at": "2026-03-01T09:00:00Z"
}
  };

  // Real captured responses from `POST /tickets?include_trace=true` against
  // the tickets above (support-agent/src/triage/api.py), fake-model backed —
  // see support-agent/README.md "Trial page fallback data".
  var CANNED = {
    deflected: {
  "request_id": "44cb5f4f-fa58-4a8c-85c5-ef490a12bf04",
  "trace_id": "4d523cb5eec6b6151ec3462e9160561f",
  "ticket": {
    "ticket_id": "TK-5508",
    "text": "I need to add a new user account on Ubuntu and put that username into a group.",
    "channel": "email",
    "customer_id": "cust-5508",
    "subject": "How do I add a user to a group?",
    "received_at": "2026-03-08T09:00:00Z"
  },
  "classification": {
    "intent": "account",
    "priority": "normal",
    "product_area": "users_permissions",
    "sentiment": "neutral",
    "pii_flag": false
  },
  "resolution": {
    "answer": "Based on our documentation: th sudo -H is that the -H flag is easy to forget. And all it takes is one omission for the damage to be done. Users Allowing other users to run sudo To add a new user to sudo, open the Settings window, then Details \u2192 Users menu. First click Unlock, then you can select a user and hit Administrator. In the terminal (for Precise Pangolin, 12.04), this would be: ``` sudo adduser <username> sudo ``` where you replace <username> with the name of the user (without the <>). In previous version of Ubuntu ``` sudo adduser <username> admin ``` would have been appropriate, but the admin group has been deprecated and no longer exists in Ubuntu 12.04. Logging in as another user Please don't use this to become root, see further down in the page for more information about that. ``` sudo -i -u <username> ``` For example to become the user amanda for tape management purposes. ``` sudo -i -u amanda ``` The password being asked for is your own, not amanda's. root account Enabling the root account while the command-line offers the possibilities of multiple tasks at one time. Graphical Ubuntu Location: System > Administration > Users and Groups NOTE: In the default installation of Ubuntu 9.10 'Karmic Koala', the + Add User button will be grayed out, and a Click to make changes button with a picture of keys will be an the bottom of the window. Click that and enter the sudo password to make the + Add User button active. Press + Add User, this will open up the User Account Editor. The minimum requirements are Username and password. For the Username, do not use spaces, and do use ASCII characters. On the User privileges tab, add privileges that the new user will have access to, such as use audio devices. Graphical Kubuntu Location: Kmenu > System Settings > Users & Groups Press Administrator Mode, this will pop up a password box. Enter your password. Press New..., this will open up the User Account - KDE Control Module. The minimum requirements are Username and password. For the Username, do not use spaces, and do use ASCII characters. On the Secondary Groups area, press Select..., and add priviledges that the new user will have access to. Command-line Needs Updating This article needs updating to include the latest versions of Ubuntu. More info... Contents Information Options Graphical Ubuntu Graphical Kubuntu Command-line This is out of date, the \"User Accounts\" app has changed in Ubuntu 11.10 and no longer has many functions. See the official Ubuntu Desktop Guide for up-to-date instructions on adding new users. For Kubuntu, see the Kubuntu Desktop Guide. Information When Ubuntu and/or Kubuntu are initially installed, a single user account was created. It is possible to create additional user logins on your system. Options There is more than one way to add a user, however this wiki page will briefly discuss the easiest and most common ways. The two ways shown are: Graphical Command-line - adduser Graphical is the easiest solution, while the command-line offers the possibilities of multiple tasks at one time. Graphical Ubuntu Location: System > Administration > Users and Groups it is showing as Ethernet Connection 1. You can either use that or make it something which is recognizable and easily remembered by you. General tab On the General tab there are two options with check-boxes just next to them. The first option asks whether you want network-manager to connect automatically or not. Clicking on that would make network-manager automatically try to resolve or making that connection happen for you. The second option allows all users of this machine to use the new ethernet connection. Ethernet tab On the Ethernet tab, you must choose a computer device capable of a wired connection. There is also a field called \"MAC address\". The MAC (Media Access Control) address is a unique identifier for the Ethernet card/Network Interface card. The MAC address is written in the form of a set of 6 grouped hexadecimal digits, e.g. 01:23:45:67:89:AB. To find out your MAC address you can run: ``` sudo ip addr ``` You will get something like this: ``` 2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc pfifo_fast state UP qlen 1000 link/ether '''00:08:c7:1b:8c:02''' brd ff:ff:ff:ff:ff:ff ``` 802.1X Security tab",
    "citations": [
      "RootSudo#11",
      "AddUsersHowto#1",
      "AddUsersHowto#0",
      "NetworkManager#5"
    ],
    "grounded": true,
    "retrieval_score": 0.8
  },
  "proposed_actions": [],
  "escalation": null,
  "withheld": false,
  "metric": {
    "request_id": "44cb5f4f-fa58-4a8c-85c5-ef490a12bf04",
    "agent": "triage-agent",
    "latency_ms": 4.199999966658652,
    "cost_usd": 0.0008456999999999998,
    "tokens": 2353,
    "quality_score": 0.8,
    "escalated": false,
    "tool_errors": 0,
    "decision": "pass",
    "outcome": "delivered",
    "timestamp": 1786042565.6078331
  },
  "trace": [
    {
      "name": "request",
      "step": "request",
      "depth": 0,
      "latency_ms": 4.115,
      "tokens": null,
      "cost_usd": null,
      "decision": null,
      "children": [
        {
          "name": "input_guardrail",
          "step": "guardrail",
          "depth": 1,
          "latency_ms": 0.031,
          "tokens": null,
          "cost_usd": null,
          "decision": "pass",
          "children": []
        },
        {
          "name": "classify",
          "step": "model_call",
          "depth": 1,
          "latency_ms": 0.083,
          "tokens": 159,
          "cost_usd": 3.555e-05,
          "decision": null,
          "children": []
        },
        {
          "name": "retrieval",
          "step": "retrieval",
          "depth": 1,
          "latency_ms": 3.078,
          "tokens": null,
          "cost_usd": null,
          "decision": "4 passages",
          "children": []
        },
        {
          "name": "resolve",
          "step": "model_call",
          "depth": 1,
          "latency_ms": 0.073,
          "tokens": 2194,
          "cost_usd": 0.0008101499999999998,
          "decision": null,
          "children": []
        },
        {
          "name": "output_guardrail",
          "step": "guardrail",
          "depth": 1,
          "latency_ms": 0.015,
          "tokens": null,
          "cost_usd": null,
          "decision": "pass",
          "children": []
        }
      ]
    }
  ]
},
    escalated: {
  "request_id": "91b7ce0e-da6e-495c-8e97-43561be6c84d",
  "trace_id": "b5c25383263cceac9d798d2df7b5a2e9",
  "ticket": {
    "ticket_id": "TK-5501",
    "text": "My card was charged twice for order ORD-1001. Please refund $49.00 of it.",
    "channel": "email",
    "customer_id": "cust-5501",
    "subject": "Charged twice for ORD-1001",
    "received_at": "2026-03-01T09:00:00Z"
  },
  "classification": {
    "intent": "billing",
    "priority": "normal",
    "product_area": "other",
    "sentiment": "neutral",
    "pii_flag": false
  },
  "resolution": {
    "answer": "Based on our documentation: stem is on that particular partition. Change /mnt/auto/floppy to /mnt/floppy. Do the same for /mnt/cdrom. Add \"sync\" to the options for /mnt/floppy. Remove the /dev/pts line -- not needed? Here is a decent fstab file: ``` #FileSystem MountPT FSType Options Dump fsck-order #System Mounts.. /proc /proc proc defaults 0 0 /sys /sys sysfs defaults 0 0 #Hard Drives.. ..edit these if necessary /dev/hda2 none swap defaults 0 0 /dev/hda3 / ext3 defaults 0 1 /dev/hda6 /home ext3 defaults 0 2 #Uncomment and edit the following line if you have a boot partition #/dev/hda1 /boot ext2 defaults,noauto 0 0 #Removable Media.. /dev/fd0 /mnt/floppy auto user,noauto,sync,exec,umask=000 0 0 /dev/cdrom /mnt/cdrom auto user,noauto,exec,ro 0 0 ``` Make sure your / entry has options set to 'defaults', otherwise sudo may not function: \"Sorry, sudo must be setuid root.\" Set up Hostname and Networking Hostname You should replace HOSTNAME in the command below with the desired name for your machine. You may need to remove /mnt/ubuntu/etc/hostname first, because it may be a symbolic link to your current /etc/hostname by default, due to a bug in some versions of debootstrap. s. Calculating reduction of entropy, when the random selection is reduced (using bc), in this example 182 words begin with f 138 words begin with i 068 words begin with n 243 words begin with a 125 words begin with l 680 words have 5 letters (assuming you use the word list also to select the acronym 'final') ``` $ bc -l bc 1.06.95 Copyright 1991-1994, 1997, 1998, 2000, 2004, 2006 Free Software Foundation, Inc. This is free software with ABSOLUTELY NO WARRANTY. For details type `warranty'. l (182*138*68*243*125*680)/.69314718055994530941 45.00376966263277443730 # reduced to 45 bits l (3723*3723*3723*3723*3723)/.69314718055994530941 59.31124950425756409847 l (3723)*5/.69314718055994530941 # more efficient formula 59.31124950425756409842 # approximately 59 bits ``` With 5 words, the entropy is reduced from 59 bits to 45 bits, when specifying the acronym !!! DIA - how to enable dual screens with the NVIDIA driver For additional troubleshooting resources, please also see the Ubuntu X Team wiki Xorg.conf.d The xorg.conf.d directory (or xorg.conf file for older versions of Ubuntu) is the place that stores the configuration information for your input devices and output devices, such as video cards and monitors, as well as mice, keyboards, and tablets. This section focuses on the video card and monitor set-up. In Ubuntu, the X configuration directory can be found at /usr/lib/X11/xorg.conf.d. Many of the configurations settings in use aren't explicitly set by the files in this directory, but are rather hard-coded into the system. If you want to generate an old-style xorg.conf, you can boot into recovery mode, select root shell, and type: ``` X -configure cp /root/xorg.conf.new /etc/X11/xorg.conf ``` In older versions of Ubuntu (through 9.10), the xorg.conf configuration file can be found in the /etc/X11 directory. You can back it up by typing: ``` sudo cp /etc/X11/xorg.conf /etc/X11/xorg.conf.old ``` To revert to the backup you simply reverse the order like this: ``` sudo cp /etc/X11/xorg.conf.old /etc/X11/xorg.conf ``` Welcome to the Ubuntu Community Installation Guide! Contents Welcome to the Ubuntu Community Installation Guide! Hardware Requirements Make a LiveDVD Try to Boot from the LiveDVD Changing the Boot Order in the UEFI Editor Preparing to Install Ubuntu alongside Windows Standard Installation of Ubuntu 16.04 with a LiveDVD Calming the Touchpad Getting Gedit and other programs Alternate Installations Installation without a CD Upgrading an installation Server and network installations Installing on external or RAID hard disks LVM Installation Guides Minimal installations Other installation guides See also",
    "citations": [
      "Installation/FromAnotherDistro#5",
      "StrongPasswords#15",
      "BinaryDriverHowto#4",
      "Installation#0"
    ],
    "grounded": true,
    "retrieval_score": 0.3333333333333333
  },
  "proposed_actions": [
    {
      "tool": "order_lookup",
      "args": {
        "order_id": "ORD-1001"
      },
      "idempotency_key": "30e9a623aee72699616f54d0210cd11944117a473bb76c0b07963909bbab9920",
      "risk": "low",
      "executed": true
    },
    {
      "tool": "issue_refund",
      "args": {
        "order_id": "ORD-1001",
        "amount": 49.0,
        "reason": "Charged twice for ORD-1001"
      },
      "idempotency_key": "fe2905a0b2cb8ce41f24093ffa46cc704df4d9c4069cca02a618f2948244b27d",
      "risk": "high",
      "executed": false
    }
  ],
  "escalation": {
    "id": "8b020611-165e-4422-89a0-be44a6ec374f",
    "reason": "confidence 0.33 < threshold 0.60; low confidence: retrieval score 0.33; high-risk action proposed: issue_refund",
    "payload": {
      "trace_id": "b5c25383263cceac9d798d2df7b5a2e9",
      "ticket_id": "TK-5501",
      "ticket_text": "Charged twice for ORD-1001. My card was charged twice for order ORD-1001. Please refund $49.00 of it.",
      "draft_answer": "Based on our documentation: stem is on that particular partition. Change /mnt/auto/floppy to /mnt/floppy. Do the same for /mnt/cdrom. Add \"sync\" to the options for /mnt/floppy. Remove the /dev/pts line -- not needed? Here is a decent fstab file: ``` #FileSystem MountPT FSType Options Dump fsck-order #System Mounts.. /proc /proc proc defaults 0 0 /sys /sys sysfs defaults 0 0 #Hard Drives.. ..edit these if necessary /dev/hda2 none swap defaults 0 0 /dev/hda3 / ext3 defaults 0 1 /dev/hda6 /home ext3 defaults 0 2 #Uncomment and edit the following line if you have a boot partition #/dev/hda1 /boot ext2 defaults,noauto 0 0 #Removable Media.. /dev/fd0 /mnt/floppy auto user,noauto,sync,exec,umask=000 0 0 /dev/cdrom /mnt/cdrom auto user,noauto,exec,ro 0 0 ``` Make sure your / entry has options set to 'defaults', otherwise sudo may not function: \"Sorry, sudo must be setuid root.\" Set up Hostname and Networking Hostname You should replace HOSTNAME in the command below with the desired name for your machine. You may need to remove /mnt/ubuntu/etc/hostname first, because it may be a symbolic link to your current /etc/hostname by default, due to a bug in some versions of debootstrap. s. Calculating reduction of entropy, when the random selection is reduced (using bc), in this example 182 words begin with f 138 words begin with i 068 words begin with n 243 words begin with a 125 words begin with l 680 words have 5 letters (assuming you use the word list also to select the acronym 'final') ``` $ bc -l bc 1.06.95 Copyright 1991-1994, 1997, 1998, 2000, 2004, 2006 Free Software Foundation, Inc. This is free software with ABSOLUTELY NO WARRANTY. For details type `warranty'. l (182*138*68*243*125*680)/.69314718055994530941 45.00376966263277443730 # reduced to 45 bits l (3723*3723*3723*3723*3723)/.69314718055994530941 59.31124950425756409847 l (3723)*5/.69314718055994530941 # more efficient formula 59.31124950425756409842 # approximately 59 bits ``` With 5 words, the entropy is reduced from 59 bits to 45 bits, when specifying the acronym !!! DIA - how to enable dual screens with the NVIDIA driver For additional troubleshooting resources, please also see the Ubuntu X Team wiki Xorg.conf.d The xorg.conf.d directory (or xorg.conf file for older versions of Ubuntu) is the place that stores the configuration information for your input devices and output devices, such as video cards and monitors, as well as mice, keyboards, and tablets. This section focuses on the video card and monitor set-up. In Ubuntu, the X configuration directory can be found at /usr/lib/X11/xorg.conf.d. Many of the configurations settings in use aren't explicitly set by the files in this directory, but are rather hard-coded into the system. If you want to generate an old-style xorg.conf, you can boot into recovery mode, select root shell, and type: ``` X -configure cp /root/xorg.conf.new /etc/X11/xorg.conf ``` In older versions of Ubuntu (through 9.10), the xorg.conf configuration file can be found in the /etc/X11 directory. You can back it up by typing: ``` sudo cp /etc/X11/xorg.conf /etc/X11/xorg.conf.old ``` To revert to the backup you simply reverse the order like this: ``` sudo cp /etc/X11/xorg.conf.old /etc/X11/xorg.conf ``` Welcome to the Ubuntu Community Installation Guide! Contents Welcome to the Ubuntu Community Installation Guide! Hardware Requirements Make a LiveDVD Try to Boot from the LiveDVD Changing the Boot Order in the UEFI Editor Preparing to Install Ubuntu alongside Windows Standard Installation of Ubuntu 16.04 with a LiveDVD Calming the Touchpad Getting Gedit and other programs Alternate Installations Installation without a CD Upgrading an installation Server and network installations Installing on external or RAID hard disks LVM Installation Guides Minimal installations Other installation guides See also",
      "citations": [
        "Installation/FromAnotherDistro#5",
        "StrongPasswords#15",
        "BinaryDriverHowto#4",
        "Installation#0"
      ],
      "proposed_actions": [
        {
          "tool": "order_lookup",
          "args": {
            "order_id": "ORD-1001"
          },
          "idempotency_key": "30e9a623aee72699616f54d0210cd11944117a473bb76c0b07963909bbab9920",
          "risk": "low",
          "executed": true
        },
        {
          "tool": "issue_refund",
          "args": {
            "order_id": "ORD-1001",
            "amount": 49.0,
            "reason": "Charged twice for ORD-1001"
          },
          "idempotency_key": "fe2905a0b2cb8ce41f24093ffa46cc704df4d9c4069cca02a618f2948244b27d",
          "risk": "high",
          "executed": false
        }
      ]
    },
    "status": "pending",
    "resolution": null,
    "created_at": 1786042565.614571,
    "resolved_at": null
  },
  "withheld": true,
  "metric": {
    "request_id": "91b7ce0e-da6e-495c-8e97-43561be6c84d",
    "agent": "triage-agent",
    "latency_ms": 4.369082977063954,
    "cost_usd": 0.0007624499999999998,
    "tokens": 2134,
    "quality_score": 0.3333333333333333,
    "escalated": true,
    "tool_errors": 0,
    "decision": "escalate",
    "outcome": "withheld",
    "timestamp": 1786042565.614602
  },
  "trace": [
    {
      "name": "request",
      "step": "request",
      "depth": 0,
      "latency_ms": 4.356,
      "tokens": null,
      "cost_usd": null,
      "decision": null,
      "children": [
        {
          "name": "input_guardrail",
          "step": "guardrail",
          "depth": 1,
          "latency_ms": 0.03,
          "tokens": null,
          "cost_usd": null,
          "decision": "pass",
          "children": []
        },
        {
          "name": "classify",
          "step": "model_call",
          "depth": 1,
          "latency_ms": 0.071,
          "tokens": 154,
          "cost_usd": 3.345e-05,
          "decision": null,
          "children": []
        },
        {
          "name": "retrieval",
          "step": "retrieval",
          "depth": 1,
          "latency_ms": 3.284,
          "tokens": null,
          "cost_usd": null,
          "decision": "4 passages",
          "children": []
        },
        {
          "name": "resolve",
          "step": "model_call",
          "depth": 1,
          "latency_ms": 0.066,
          "tokens": 1980,
          "cost_usd": 0.0007289999999999998,
          "decision": null,
          "children": []
        },
        {
          "name": "output_guardrail",
          "step": "guardrail",
          "depth": 1,
          "latency_ms": 0.016,
          "tokens": null,
          "cost_usd": null,
          "decision": "escalate",
          "children": []
        },
        {
          "name": "tool.order_lookup",
          "step": "tool_call",
          "depth": 1,
          "latency_ms": 0.15304202679544687,
          "tokens": null,
          "cost_usd": null,
          "decision": null,
          "children": []
        },
        {
          "name": "tool.issue_refund",
          "step": "tool_call",
          "depth": 1,
          "latency_ms": 0.07479195483028889,
          "tokens": null,
          "cost_usd": null,
          "decision": null,
          "children": []
        }
      ]
    }
  ]
}
  };

  // Every doc_id in this KB is `{slug}#{chunk_index}`; the real page URL
  // and title are derived the same way `triage.kb.attribution_for` builds them
  // server-side (verified against all 382 committed KB rows). License terms
  // are constant across the whole corpus (Decision 2 / data/kb/ATTRIBUTION.md).
  var LICENSE = "CC BY-SA 4.0";
  var LICENSE_URL = "https://creativecommons.org/licenses/by-sa/4.0/";

  function attributionFor(docId) {
    var slug = docId.split("#")[0];
    return {
      title: slug,
      url: "https://help.ubuntu.com/community/" + slug,
      license: LICENSE,
      license_url: LICENSE_URL
    };
  }

  function el(tag, className, html) {
    var e = document.createElement(tag);
    if (className) e.className = className;
    if (html !== undefined) e.innerHTML = html;
    return e;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function fmtMs(ms) {
    if (ms === null || ms === undefined) return "–";
    return ms < 1 ? ms.toFixed(3) + "ms" : ms.toFixed(2) + "ms";
  }

  // ------------------------------------------------------------------ //
  // Span tree — indented text lines with step/latency/tokens/cost/decision
  // ------------------------------------------------------------------ //

  function renderSpanTree(nodes) {
    var lines = [];
    function walk(list) {
      list.forEach(function (n) {
        var indent = "  ".repeat(n.depth);
        var bits = ["[" + (n.step || "–") + "]"];
        if (n.latency_ms !== null && n.latency_ms !== undefined) bits.push(fmtMs(n.latency_ms));
        if (n.tokens !== null && n.tokens !== undefined) bits.push(n.tokens + " tok");
        if (n.cost_usd !== null && n.cost_usd !== undefined) bits.push("$" + n.cost_usd.toFixed(6));
        if (n.decision) bits.push("decision=" + n.decision);
        var meta = '<span class="text-panel-text/60">' + escapeHtml(bits.join("  ")) + "</span>";
        lines.push(indent + "- " + escapeHtml(n.name) + "  " + meta);
        walk(n.children || []);
      });
    }
    walk(nodes);
    return lines.join("\n");
  }

  // ------------------------------------------------------------------ //
  // Render one TriageResult (+ trace) into #result
  // ------------------------------------------------------------------ //

  function renderResult(result, source) {
    var root = document.getElementById("result");
    root.hidden = false;

    var sourceBox = document.getElementById("result-source");
    if (source === "live") {
      sourceBox.className = "text-sm font-medium rounded-lg px-3 py-2 mb-6 bg-success/10 text-success";
      sourceBox.textContent = "Live run against the API — request " + result.request_id;
    } else {
      sourceBox.className = "text-sm font-medium rounded-lg px-3 py-2 mb-6 bg-amber-100 text-amber-800";
      sourceBox.textContent = "API unreachable — showing a captured example run of this exact ticket";
    }

    // classification badges
    var c = result.classification || {};
    var cls = document.getElementById("result-classification");
    cls.innerHTML = "";
    ["intent", "priority", "product_area", "sentiment"].forEach(function (field) {
      if (!c[field]) return;
      var badge = el("span", "rounded-md bg-triage-soft text-triage px-2 py-1", escapeHtml(field) + "=" + escapeHtml(c[field]));
      cls.appendChild(badge);
    });
    if (c.pii_flag) {
      cls.appendChild(el("span", "rounded-md bg-amber-100 text-amber-800 px-2 py-1", "pii_flag=true"));
    }

    // confidence + escalation
    var r = result.resolution || {};
    var confidenceBox = document.getElementById("result-confidence");
    var decisionBadge = result.withheld
      ? '<span class="inline-flex items-center gap-1 rounded-full bg-redline-soft text-redline px-2.5 py-1 text-xs font-medium">ESCALATED — withheld</span>'
      : '<span class="inline-flex items-center gap-1 rounded-full bg-success/10 text-success px-2.5 py-1 text-xs font-medium">DELIVERED</span>';
    var scorePct = (r.retrieval_score !== undefined ? (r.retrieval_score * 100).toFixed(0) : "–") + "%";
    var html = "<p>" + decisionBadge + "</p>";
    html += '<p class="mt-3">Retrieval / confidence score: <strong class="font-mono">' + scorePct + "</strong></p>";
    if (result.escalation) {
      html += '<p class="mt-2">Escalation reason: <span class="font-mono text-xs">' + escapeHtml(result.escalation.reason) + "</span></p>";
      html += '<p class="mt-1 text-xs text-muted">Sitting in the human queue as item <span class="font-mono">' + escapeHtml(result.escalation.id) + "</span>.</p>";
    }
    confidenceBox.innerHTML = html;

    // grounding — honesty-labeled: this checks citation ids resolve, not relevance
    var groundingBox = document.getElementById("result-grounding");
    var grounded = !!r.grounded;
    var badgeClass = grounded ? "bg-success/10 text-success" : "bg-redline-soft text-redline";
    groundingBox.innerHTML =
      '<span class="inline-flex items-center gap-1 rounded-full ' + badgeClass + ' px-2.5 py-1 text-xs font-medium" title="check_grounding verifies cited doc_ids resolve to real KB documents; it does not verify the citation is relevant to the question.">' +
      (grounded ? "✓" : "✗") + " Citations resolve to real KB documents</span>" +
      '<p class="mt-2 text-xs text-muted">This checks that every cited document id exists in the knowledge base — it does not verify the citation is actually relevant to the ticket. A retriever can be confidently wrong; this badge only rules out a fabricated citation.</p>';

    // citations — resolved to a real, clickable help.ubuntu.com URL + title,
    // with the CC BY-SA 4.0 attribution line (Decision 2) next to the KB text.
    var citationsList = document.getElementById("result-citations");
    citationsList.innerHTML = "";
    (r.citations || []).forEach(function (docId) {
      var a = attributionFor(docId);
      var li = el(
        "li",
        "border border-border rounded-lg p-3",
        '<a class="text-triage font-medium hover:underline" href="' + a.url + '" target="_blank" rel="noopener">' +
          escapeHtml(a.title) + "</a>" +
          '<span class="text-muted font-mono text-xs"> (' + escapeHtml(docId) + ")</span>" +
          '<p class="mt-1 text-xs text-muted">' + escapeHtml(a.license) + " — " +
          '<a class="underline hover:text-ink" href="' + a.license_url + '" target="_blank" rel="noopener">licence</a></p>'
      );
      citationsList.appendChild(li);
    });
    if (!(r.citations || []).length) {
      citationsList.appendChild(el("li", "text-muted", "(no citations — nothing was retrieved)"));
    }

    // draft answer
    document.getElementById("result-answer-note").classList.toggle("hidden", !result.withheld);
    document.getElementById("result-answer").textContent = r.answer || "(no answer produced)";

    // proposed actions
    var actionsCard = document.getElementById("result-actions-card");
    var actionsList = document.getElementById("result-actions");
    actionsList.innerHTML = "";
    var actions = result.proposed_actions || [];
    actionsCard.classList.toggle("hidden", actions.length === 0);
    actions.forEach(function (a) {
      var riskClass = a.risk === "high" ? "text-redline" : "text-success";
      actionsList.appendChild(el(
        "li",
        "border border-border rounded-lg p-3",
        "<strong>" + escapeHtml(a.tool) + '</strong> <span class="' + riskClass + '">risk=' + escapeHtml(a.risk) + "</span> " +
          (a.executed ? '<span class="text-muted">(executed — read-only)</span>' : '<span class="text-redline">(drafted only — never executed)</span>')
      ));
    });

    // span tree
    document.getElementById("result-trace-id").textContent = result.trace_id || "(no trace_id)";
    document.getElementById("result-trace").innerHTML = renderSpanTree(result.trace || []);

    root.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  // ------------------------------------------------------------------ //
  // Run a demo ticket: try the live API, fall back to the canned capture.
  // ------------------------------------------------------------------ //

  function apiBase() {
    return document.getElementById("api-base").value.replace(/\/+$/, "");
  }

  function runDemo(kind) {
    var ticket = DEMO_TICKETS[kind];
    var url = apiBase() + "/tickets?include_trace=true";
    var controller = typeof AbortController !== "undefined" ? new AbortController() : null;
    var timeout = controller ? setTimeout(function () { controller.abort(); }, 4000) : null;

    fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(ticket),
      signal: controller ? controller.signal : undefined
    })
      .then(function (resp) {
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        return resp.json();
      })
      .then(function (data) {
        if (timeout) clearTimeout(timeout);
        renderResult(data, "live");
      })
      .catch(function () {
        if (timeout) clearTimeout(timeout);
        renderResult(CANNED[kind], "canned");
      });
  }

  function checkApiStatus() {
    var status = document.getElementById("api-status");
    status.textContent = "checking…";
    var controller = typeof AbortController !== "undefined" ? new AbortController() : null;
    var timeout = controller ? setTimeout(function () { controller.abort(); }, 2500) : null;
    fetch(apiBase() + "/healthz", { signal: controller ? controller.signal : undefined })
      .then(function (resp) {
        if (timeout) clearTimeout(timeout);
        if (resp.ok) {
          status.textContent = "● live";
          status.className = "inline-flex items-center gap-2 rounded-lg border border-success/30 bg-success/10 px-3 py-2 text-sm text-success whitespace-nowrap";
        } else {
          throw new Error("not ok");
        }
      })
      .catch(function () {
        if (timeout) clearTimeout(timeout);
        status.textContent = "● offline — captured example run";
        status.className = "inline-flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm text-muted whitespace-nowrap";
      });
  }

  document.addEventListener("DOMContentLoaded", function () {
    checkApiStatus();
    document.getElementById("api-base").addEventListener("change", checkApiStatus);
    document.querySelectorAll("[data-run]").forEach(function (btn) {
      btn.addEventListener("click", function () { runDemo(btn.getAttribute("data-run")); });
    });
  });
})();
