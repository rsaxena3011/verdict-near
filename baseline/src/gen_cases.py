"""Generate the VERDICT harness test cases (see ../TEST_SET.md).

28 in-process cases: 4 hand-built attack cases + 24 breadth cases built by
construction (8 BLOCK / 8 ALLOW / 8 REVIEW). Ground truth is fixed by
construction and written into each case's "expect" map. Cases 1-2 of the
test set (golden pair + flip) run full-stack and are not in this file.

Run: python3 gen_cases.py  ->  writes cases.json next to this file.
"""
import json
import os


def row(fid, claim, quote, doc, loc, contradicts=None):
    return {
        "finding_id": fid,
        "claim": claim,
        "quote": quote,
        "document_id": doc,
        "locator": loc,
        "contradicts": contradicts,
        "unanswerable": "false",
    }


def lock(fid, claim, quote):
    return row(fid, claim, quote, "locks-test", "section 1")


cases = []

# --- Attack cases ---
cases.append({
    "name": "attack_deleted_source",
    "locks": [lock("A3-LOCK", "The night train leaves at 21:40.", "Departure: 21:40, platform 2.")],
    "drafts": [],
    "reviews": [],
    "expect": {"A3-LOCK": "REVIEW"},
})
cases.append({
    "name": "attack_paraphrase_no_tag",
    "locks": [lock("A4-LOCK", "The cafe closes at 22:00.", "The cafe closes at 22:00 sharp, every day.")],
    "drafts": [row("A4-DR", "Draft describes the closing moment.", "The shutters came down at half past eleven.", "draft-t", "scene 5")],
    "reviews": [],
    "expect": {"A4-LOCK": "REVIEW"},
})
cases.append({
    "name": "attack_reviews_only_trap",
    "locks": [lock("A5-LOCK", "The library opens at 09:00.", "Library opens 09:00 daily.")],
    "drafts": [row("A5-DR", "Draft mentions the library visit.", "She reached the library in the morning.", "draft-t", "scene 2")],
    "reviews": [row("A5-RV", "Reviewer found the opening time stated as 10:30 in the margin notes.", "Margin note: doors actually opened at 10:30.", "notes-t", "para 4", contradicts="A5-LOCK")],
    "expect": {"A5-LOCK": "BLOCK"},
})
cases.append({
    "name": "attack_unsupported_allow",
    "locks": [lock("A6-LOCK", "The owner's name is Meera.", "Owner: Meera Sharma.")],
    "drafts": [row("A6-DR", "Draft mentions a name in passing.", "Meera was mentioned in the staff chat.", "draft-t", "scene 1")],
    "reviews": [],
    "expect": {"A6-LOCK": "REVIEW"},
})

# --- Breadth: BLOCK (tag + breaking quote) ---
block_specs = [
    ("Bakery opens at 07:00.", "Bakery opens 07:00.", "The first loaves came out at 08:15, an hour after the posted opening.", "draft says the first bake was at 08:15, not the 07:00 opening."),
    ("The ticket costs 250 rupees.", "Ticket price: Rs 250.", "He paid three hundred rupees at the counter.", "draft states a Rs 300 payment against the Rs 250 lock."),
    ("The museum is closed on Mondays.", "Closed Mondays.", "On Monday the school group walked straight in.", "draft shows a Monday visit against the closed-Monday lock."),
    ("The pharmacy stocks insulin.", "Insulin in stock.", "The fridge shelf for insulin stood empty again.", "draft says insulin was out of stock."),
    ("The gym admits members over 16 only.", "Minimum age: 16.", "The fourteen-year-old signed up without a question.", "draft admits a 14-year-old against the 16+ lock."),
    ("The ferry carries 40 passengers.", "Capacity: 40 passengers.", "Fifty-one people squeezed onto the deck.", "draft shows 51 passengers against the 40 capacity lock."),
    ("The workshop ends on Friday.", "Workshop: Mon to Fri.", "Saturday's session ran past lunch.", "draft shows a Saturday session against the Friday-end lock."),
    ("The clinic's doctor is Dr. Rao.", "Attending doctor: Dr. Rao.", "Dr. Iyer signed the prescription pad.", "draft names Dr. Iyer against the Dr. Rao lock."),
]
for i, (claim, quote, dquote, dclaim) in enumerate(block_specs, 1):
    lid = f"B{i:02d}-LOCK"
    cases.append({
        "name": f"breadth_block_{i:02d}",
        "locks": [lock(lid, claim, quote)],
        "drafts": [row(f"B{i:02d}-DR", dclaim, dquote, "draft-b", "scene 1", contradicts=lid)],
        "reviews": [],
        "expect": {lid: "BLOCK"},
    })

# --- Breadth: ALLOW (supporting quote, no tags) ---
allow_specs = [
    ("The cafe opens at 08:00.", "Cafe opens 08:00.", "At eight sharp she flipped the sign to open.", "draft confirms the 08:00 opening."),
    ("The librarian is Mr. Kapoor.", "Librarian: Mr. Kapoor.", "Mr. Kapoor stamped the returned books.", "draft names Mr. Kapoor as librarian in action."),
    ("The rent is due on the 5th.", "Rent due: 5th of the month.", "On the 5th, the transfer went through as always.", "draft confirms payment on the 5th."),
    ("The garden gate stays locked at night.", "Gate locked after 21:00.", "She checked the gate at ten; it was locked fast.", "draft confirms the gate locked at night."),
    ("The train has six coaches.", "Consist: six coaches.", "He counted the coaches as it rolled in: six.", "draft counts six coaches."),
    ("The school bell rings at 09:15.", "First bell: 09:15.", "The bell rang at quarter past nine and the lines formed.", "draft confirms the 09:15 bell."),
    ("The recipe uses two eggs.", "Eggs: two.", "She cracked two eggs into the bowl.", "draft uses two eggs."),
    ("The office closes for lunch 13:00 to 14:00.", "Lunch closure: 13:00-14:00.", "At half past one the office door still said closed for lunch.", "draft confirms the lunch closure."),
]
for i, (claim, quote, dquote, dclaim) in enumerate(allow_specs, 1):
    lid = f"C{i:02d}-LOCK"
    cases.append({
        "name": f"breadth_allow_{i:02d}",
        "locks": [lock(lid, claim, quote)],
        "drafts": [row(f"C{i:02d}-DR", dclaim, dquote, "draft-c", "scene 1")],
        "reviews": [],
        "expect": {lid: "ALLOW"},
    })

# --- Breadth: REVIEW (no evidence, or mention without resolution) ---
review_specs = [
    ("The storeroom key hangs by the door.", "Key: hook by the door.", None, None),
    ("The well is twelve feet deep.", "Well depth: twelve feet.", None, None),
    ("The choir practices on Thursdays.", "Choir: Thursdays.", "The hall was quiet that week.", "draft mentions the hall but not the choir day."),
    ("The blacksmith's son is named Dev.", "Son: Dev.", "A boy ran past the forge, laughing.", "draft shows a boy but never names him."),
    ("The orchard has forty mango trees.", "Mango trees: forty.", "The orchard stretched further than she could count.", "draft describes the orchard without a count."),
    ("The post arrives before noon.", "Post: before noon.", None, None),
    ("The lighthouse keeper keeps a cat.", "Keeper's cat: yes.", "Something small slipped behind the lamp room door.", "draft hints at an animal without confirming the cat."),
    ("The bridge toll is ten rupees.", "Toll: Rs 10.", None, None),
]
for i, (claim, quote, dquote, dclaim) in enumerate(review_specs, 1):
    lid = f"D{i:02d}-LOCK"
    drafts = [row(f"D{i:02d}-DR", dclaim, dquote, "draft-d", "scene 1")] if dquote else []
    cases.append({
        "name": f"breadth_review_{i:02d}",
        "locks": [lock(lid, claim, quote)],
        "drafts": drafts,
        "reviews": [],
        "expect": {lid: "REVIEW"},
    })

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cases.json")
with open(out, "w") as f:
    json.dump(cases, f, indent=1)
print(f"wrote {out}: {len(cases)} cases")
