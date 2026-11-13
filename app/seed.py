"""Demo brand library for a FICTIONAL company ("Lumora", smart home lighting).

All guidelines, facts and numbers below are invented for demonstration. No real
organisation's confidential material is used.
"""

BRAND = {
    "name": "Lumora",
    "tagline": "Light that listens",
    "palette": [
        {"name": "Lumora Amber", "hex": "#F5A623"},
        {"name": "Midnight Navy", "hex": "#14213D"},
        {"name": "Warm White", "hex": "#FFF8EC"},
        {"name": "Slate", "hex": "#3D4A5C"},
        {"name": "Sage", "hex": "#7FA88B"},
    ],
    "allowed_caps": ["USB", "WIFI", "HDMI", "FAQ", "LED", "CEO", "USA", "IST", "AI", "TV", "PDF"],
}

USERS = [
    {"id": "u_alex", "name": "Alex (Creator)", "role": "creator"},
    {"id": "u_sam", "name": "Sam (Creator)", "role": "creator"},
    {"id": "u_morgan", "name": "Morgan (Brand Manager)", "role": "manager"},
    {"id": "u_riley", "name": "Riley (Compliance Reviewer)", "role": "reviewer"},
]

# kind: term | pattern | require | claim | competitor | caps | exclaim | link | longsentence
RULES = [
    # ---- Terminology
    dict(id="BG-1.1", category="terminology", title="Use 'members', not 'users'", severity="medium", kind="term",
         text="We call the people who use Lumora products 'members'. Never refer to them as 'users' or 'customers' in public copy.",
         config={"banned": ["users", "user", "customers", "customer"], "preferred": "member(s)",
                 "map": {"users": "members", "user": "member", "customers": "members", "customer": "member"}}),
    dict(id="BG-1.2", category="terminology", title="Write 'Lumora Hub' as two words", severity="medium", kind="term",
         text="The product name is 'Lumora Hub' (two words, capital H). Do not write LumoraHub, Lumora hub or Lumora-Hub.",
         config={"banned": ["LumoraHub", "Lumora-Hub", "Lumora hub", "lumorahub"], "preferred": "Lumora Hub",
                 "map": {"lumorahub": "Lumora Hub", "lumora-hub": "Lumora Hub", "lumora hub": "Lumora Hub"},
                 "case_sensitive_exact": True}),
    dict(id="BG-1.3", category="terminology", title="Brand name is always capitalised", severity="low", kind="term",
         text="'Lumora' always starts with a capital L in running text.",
         config={"banned": ["lumora"], "preferred": "Lumora", "map": {"lumora": "Lumora"}, "case_sensitive": True}),
    dict(id="BG-1.4", category="terminology", title="Use 'affordable' or 'great value', not 'cheap'", severity="medium", kind="term",
         text="Never describe Lumora products as 'cheap'. Use 'affordable' or 'great value'.",
         config={"banned": ["cheap", "cheapest"], "preferred": "affordable",
                 "map": {"cheap": "affordable", "cheapest": "most affordable"}}),
    dict(id="BG-1.5", category="terminology", title="Inclusive address", severity="low", kind="term",
         text="Address audiences with 'everyone' or 'friends'. Do not use 'guys'.",
         config={"banned": ["guys"], "preferred": "everyone", "map": {"guys": "everyone"}}),
    # ---- Tone
    dict(id="BG-2.1", category="tone", title="At most one exclamation mark", severity="low", kind="exclaim",
         text="Our voice is calm and warm. Use no more than one exclamation mark in any piece of content.",
         config={"max": 1}),
    dict(id="BG-2.2", category="tone", title="No shouting (ALL CAPS)", severity="medium", kind="caps",
         text="Do not write whole words in capital letters for emphasis. Approved acronyms are exempt.",
         config={}),
    dict(id="BG-2.3", category="tone", title="No pressure or urgency tactics", severity="medium", kind="pattern",
         text="Lumora never pressures members. Avoid phrases such as 'hurry', 'act now', 'last chance' or \"don't miss out\".",
         config={"pattern": r"\b(hurry|act now|last chance|don'?t miss out|limited time only|while stocks? last)\b",
                 "suggestion": "Replace with a calm, factual invitation, e.g. 'Available until 30 November'."}),
    dict(id="BG-2.4", category="tone", title="Avoid slang", severity="low", kind="pattern",
         text="Keep language friendly but professional. Avoid slang such as 'gonna', 'wanna', 'awesome' or 'stuff'.",
         config={"pattern": r"\b(gonna|wanna|gotta|awesome|stuff|super cool)\b",
                 "map": {"gonna": "going to", "wanna": "want to", "gotta": "need to", "awesome": "excellent",
                         "stuff": "products", "super cool": "impressive"}}),
    # ---- Claims
    dict(id="BG-3.1", category="claims", title="No unsupported superlatives", severity="high", kind="claim",
         text="Superlatives such as 'best', '#1' or 'leading' may only be used when an approved fact in the Facts library supports them.",
         config={"mode": "superlative"}),
    dict(id="BG-3.2", category="claims", title="No absolute promises", severity="high", kind="claim",
         text="Do not make absolute promises ('guaranteed', '100%', 'always', 'risk-free', 'clinically proven') unless legal has approved the wording.",
         config={"mode": "absolute"}),
    dict(id="BG-3.3", category="claims", title="Health and safety claims need legal approval", severity="high", kind="claim",
         text="Lumora lighting must not be described as curing, treating or preventing any medical condition.",
         config={"mode": "health"}),
    # ---- Messaging
    dict(id="BG-4.1", category="messaging", title="Do not name competitors", severity="high", kind="competitor",
         text="Never mention or compare ourselves with competitors by name.",
         config={"names": ["Philips Hue", "Hue", "IKEA Tradfri", "Tradfri", "LIFX", "Nanoleaf", "Wiz"]}),
    dict(id="BG-4.2", category="messaging", title="Promotions must include 'Terms apply'", severity="high", kind="require",
         text="Any content that mentions a discount, sale or '% off' must include the words 'Terms apply'.",
         config={"trigger": r"(\b\d{1,3}\s?%\s?off\b|\bdiscount\b|\bsale\b|\bpromo(?:tion)?\b|\bcoupon\b)",
                 "required": "Terms apply", "append": "Terms apply."}),
    # ---- Accessibility
    dict(id="BG-5.1", category="accessibility", title="Descriptive link text", severity="medium", kind="link",
         text="Links must describe their destination. Do not use 'click here' or 'read more' as link text.",
         config={"bad": ["click here", "here", "read more", "link", "this link"]}),
    dict(id="BG-5.2", category="accessibility", title="Images need alt text", severity="high", kind="alt",
         text="Every image must have alt text that describes what it shows.", config={}),
    dict(id="BG-5.3", category="accessibility", title="Readable sentences", severity="low", kind="longsentence",
         text="Keep sentences under 30 words so they are easy to read, including for screen-reader users.",
         config={"max_words": 30}),
    dict(id="BG-5.4", category="accessibility", title="Text colour contrast (WCAG AA)", severity="high", kind="contrast",
         text="Text must have a contrast ratio of at least 4.5:1 against its background.", config={"min": 4.5}),
    # ---- Visual
    dict(id="BG-6.1", category="visual", title="Use approved brand colours", severity="medium", kind="palette",
         text="Designs may only use colours from the approved Lumora palette (neutral black, white and grey are also allowed).",
         config={"tolerance": 60}),
]

FACTS = [
    dict(id="F-1", statement="Lumora was founded in 2019.", keywords=["lumora", "founded"], valid_until=None,
         supports=[], owner="Brand team", source="Company fact sheet v3"),
    dict(id="F-2", statement="The Lumora Hub connects up to 64 bulbs.", keywords=["hub", "bulbs"], valid_until=None,
         supports=[], owner="Product team", source="Hub spec sheet v2"),
    dict(id="F-3", statement="Lumora Smart Bulbs use up to 80% less energy than traditional incandescent bulbs.",
         keywords=["bulb", "energy"], valid_until=None, supports=[], owner="Product team", source="Lab test report LT-14"),
    dict(id="F-4", statement="Lumora offers free delivery on orders over $50.", keywords=["free", "delivery"],
         valid_until=None, supports=[], owner="Commerce team", source="Shipping policy 2026"),
    dict(id="F-5", statement="Lumora Smart Bulbs have a 3-year warranty.", keywords=["bulb", "warranty"],
         valid_until=None, supports=[], owner="Legal", source="Warranty terms 2026"),
    dict(id="F-6", statement="Spring Sale: 20% off all bulbs, ended 31 March 2026.", keywords=["spring", "sale"],
         valid_until="2026-03-31", supports=[], owner="Commerce team", source="Promotion calendar"),
    dict(id="F-7", statement="Rated 4.7 out of 5 by 12,000 members in the 2026 member survey, which supports calling Lumora 'highly rated'.",
         keywords=["rated"], valid_until=None, supports=["highly rated", "well-rated", "top-rated"],
         owner="Insights team", source="Member survey 2026"),
]

LIBRARY_SETTINGS = BRAND
