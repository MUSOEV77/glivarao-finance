"""Reviewed editorial explanations used by the free (offline) script writer, per topic family.

Rules for this file: general, durable explanations only; no year-specific figures, no statistics (numbers come
from research data or calculators at run time); accurate for both the US and Canada unless marked.
Each entry: (heading, narration, illustration, set). Narration may use *emphasis* markers.
"""
from __future__ import annotations

LIB = {
    "card": {
        "how": [
            ("How card interest works", "Credit card interest is quoted as an annual rate, the APR. But it's charged in "
             "small slices. Each month, the card takes roughly one twelfth of that rate and applies it to the balance "
             "you're carrying. Pay the full statement balance by the due date, and on most cards you pay no interest on "
             "new purchases at all. Carry a balance, and that monthly slice keeps landing, month after month.",
             "credit_card", "studio"),
            ("The minimum payment", "The minimum payment is designed to keep your account in good standing, not to get "
             "you out of debt. It's usually a small percentage of the balance plus that month's interest. So when you "
             "pay only the minimum, most of your money goes to interest, and the balance barely moves.",
             "warning", "home"),
        ],
        "mistakes": [
            ("Mistake: only the minimum", "The first mistake is treating the minimum as the plan. It's a floor, not a "
             "target. Even a modest fixed payment above the minimum changes the timeline dramatically, as the math "
             "just showed.", "warning", "home"),
            ("Mistake: ignoring the statement", "The second mistake is not reading the statement. Fees, a promotional "
             "rate that expired, or a charge you don't recognize can all hide in plain sight. If something looks wrong, "
             "dispute it quickly. Card issuers have formal dispute processes, and acting fast matters.",
             "paycheck", "bank"),
        ],
        "angle_extra": {
            "triggers": ["statement", "purchase", "dispute", "charge"],
            "scene": ("If a charge looks wrong", "If a charge on your statement looks wrong, act quickly. Contact "
                      "your card issuer, explain the problem, and follow up in writing. Keep receipts, emails and "
                      "screenshots. In the US, the Fair Credit Billing Act generally gives you sixty days from the "
                      "statement date to dispute a billing error. In Canada, contact your issuer right away and ask "
                      "about their dispute and chargeback process.", "paycheck", "bank"),
        },
        "actions": ["Pick a fixed monthly payment above the minimum, and automate it",
                    "Put extra money toward the highest-APR card first",
                    "Read every statement and dispute errors right away"],
    },
    "loan": {
        "how": [
            ("How loan payments work", "Most mortgages, car loans and student loans are amortizing loans. Your monthly "
             "payment stays the same, but what's inside it changes. Early on, a big share of each payment is interest. "
             "Over time, more and more goes to the actual balance.", "house", "home"),
            ("Why the rate matters", "Because interest is charged on the remaining balance for years, even a small "
             "difference in the rate adds up. That's why it pays to compare offers from several lenders, and to "
             "understand every fee, not just the monthly payment.", "scale", "bank"),
        ],
        "mistakes": [
            ("Mistake: shopping by payment", "A common mistake is shopping only by the monthly payment. A longer term "
             "can make the payment smaller while making the total cost much bigger.", "warning", "bank"),
            ("Mistake: waiting too long", "Another mistake is staying silent when money gets tight. If you think "
             "you'll miss a payment, contact your lender early and ask what hardship options exist. Lenders usually "
             "have more options before an account falls behind than after.", "calendar", "home"),
        ],
        "actions": ["Compare the total cost of a loan, not just the payment",
                    "Get quotes from several lenders",
                    "Call your lender early if you might miss a payment"],
    },
    "credit_file": {
        "how": [
            ("What's in a credit report", "Your credit report is a record of your borrowing: your accounts, your "
             "balances, and whether you paid on time. Lenders, landlords and some employers look at it. Your credit "
             "score is calculated from that report, so if the report is wrong, the score can be wrong too.",
             "paycheck", "studio"),
            ("Where errors come from", "Errors happen more than people think. Accounts get mixed up between people "
             "with similar names, a paid debt still shows as unpaid, or an account that isn't yours appears because "
             "of identity theft.", "warning", "bank"),
        ],
        "mistakes": [
            ("Mistake: never checking", "The biggest mistake is never looking. In the US, you can get free credit "
             "reports from all three national bureaus at AnnualCreditReport dot com. In Canada, Equifax and TransUnion "
             "both offer free access to your credit report.", "lightbulb", "studio"),
            ("Mistake: disputing without proof", "The second mistake is disputing without documents. Keep copies of "
             "statements, letters and payment confirmations, and send them with your dispute.", "paycheck", "home"),
        ],
        "actions": ["Check your credit reports from each bureau",
                    "Dispute any error in writing, with documents",
                    "Consider a credit freeze if you suspect identity theft"],
    },
    "scam": {
        "how": [
            ("How scams work", "Almost every money scam follows the same script. Create urgency, pretend to be "
             "someone you trust, and get you to pay in a way that's hard to reverse, like a wire transfer, gift cards, "
             "a payment app, or cryptocurrency.", "warning", "city"),
            ("The red flags", "So watch for the red flags. Pressure to act right now. A request to keep it secret. "
             "A message that says it's your bank, the government, or a delivery company, but came out of nowhere. "
             "And any promise of returns that sound too good to be true.", "shield", "studio"),
        ],
        "mistakes": [
            ("Mistake: trusting caller ID", "A common mistake is trusting caller ID or a familiar logo. Both can be "
             "faked. If a call or message worries you, hang up and contact the company yourself, using the number on "
             "your card or their official website.", "warning", "home"),
            ("Mistake: staying quiet", "Another mistake is staying quiet out of embarrassment. Report it. In the US, "
             "you can report fraud to the Federal Trade Commission at Report Fraud dot F T C dot gov. In Canada, "
             "contact the Canadian Anti-Fraud Centre. And tell your bank right away.", "shield", "bank"),
        ],
        "actions": ["Slow down when someone pressures you to pay",
                    "Verify by contacting the company yourself",
                    "Report scams and tell your bank immediately"],
    },
    "grow": {
        "how": [
            ("How growth compounds", "Compounding means your money earns returns, and then those returns earn "
             "returns too. In the early years, the growth looks tiny. Later, it can become the biggest part of the "
             "total. The key ingredient isn't a big starting amount. It's time.", "growth_arrow", "studio"),
            ("Make it automatic", "The most reliable way to save is to make it automatic. Move a set amount on payday, "
             "before you have a chance to spend it. Tax-advantaged accounts can help too, like a 401(k) or IRA in the "
             "US, or a TFSA or RRSP in Canada.", "piggy_bank", "home"),
        ],
        "mistakes": [
            ("Mistake: waiting to start", "The biggest mistake is waiting for the perfect moment. Starting smaller but "
             "sooner usually beats starting bigger but later.", "hourglass", "studio"),
            ("Mistake: no safety net", "Another mistake is investing without an emergency fund. Without a cash "
             "cushion, a surprise bill can push you into high-interest debt, which undoes your progress.", "shield", "home"),
        ],
        "actions": ["Automate a set amount every payday",
                    "Build a cash cushion before taking investment risk",
                    "Use the tax-advantaged accounts available to you"],
    },
    "invest": {
        "how": [
            ("What you actually own", "When you invest in a stock, you own a small piece of a company. A fund holds "
             "many investments at once, and an index fund simply tracks a whole market index. That spreads your risk "
             "across many companies instead of betting on one.", "growth_arrow", "studio"),
            ("Risk comes with return", "Investments that can grow more can also fall more, sometimes for years. "
             "That's why money you need soon usually belongs somewhere safer, and long-term money can take more "
             "risk.", "scale", "city"),
        ],
        "mistakes": [
            ("Mistake: ignoring fees", "A quiet mistake is ignoring fees. A one percent annual fee doesn't sound like "
             "much, but it's charged every year, on your whole balance.", "warning", "bank"),
            ("Mistake: chasing headlines", "Another mistake is buying after big gains and selling after big drops. "
             "Reacting to headlines tends to mean buying high and selling low.", "warning", "city"),
        ],
        "actions": ["Know exactly what you own and what it costs",
                    "Match your risk to when you'll need the money",
                    "Keep fees low and stay diversified"],
    },
    "bank": {
        "how": [
            ("Where fees hide", "Banks earn money from fees: monthly maintenance fees, overdraft fees, out-of-network "
             "ATM fees and foreign transaction fees. Many of them can be avoided once you know the rules on your "
             "account.", "bank", "bank"),
            ("Is your money protected?", "Deposits at insured banks are protected up to limits. In the US that's the "
             "FDIC, which covers up to two hundred fifty thousand dollars per depositor, per insured bank, for each "
             "account ownership category. In Canada, CDIC covers eligible deposits up to one hundred thousand dollars "
             "per category at member institutions.", "shield", "bank"),
        ],
        "mistakes": [
            ("Mistake: payment apps as a bank", "A common mistake is treating payment apps like a bank account. "
             "Sending money to the wrong person, or to a scammer, can be very hard to undo. Double-check every "
             "recipient.", "warning", "city"),
            ("Mistake: paying avoidable fees", "Another mistake is paying fees out of habit. Ask your bank which fees "
             "you can avoid, or compare other accounts.", "paycheck", "home"),
        ],
        "actions": ["Review your account's fee schedule",
                    "Double-check every payment-app recipient",
                    "Know your deposit insurance coverage"],
    },
    "generic": {
        "how": [
            ("Start with the basics", "Most money problems get easier once you can see the whole picture: what comes "
             "in, what goes out, what you owe, and what it costs you. Write it down once, and patterns jump out.",
             "paycheck", "studio"),
            ("Decide, then automate", "Good money habits work best when they don't rely on willpower. Make the "
             "decision once, then automate it, so it keeps happening even on busy months.", "calendar", "home"),
        ],
        "mistakes": [
            ("Mistake: guessing", "The most common mistake is guessing instead of checking the numbers.", "warning",
             "studio"),
            ("Mistake: going it alone", "Another is not asking for help. Many banks, lenders and nonprofit credit "
             "counselors offer free guidance.", "lightbulb", "home"),
        ],
        "actions": ["Write down your real numbers",
                    "Automate the decisions you've made",
                    "Ask questions before you sign anything"],
    },
}


# Reviewed myth / fact pairs for the Myth vs Fact format: (myth stated fairly, the fact, illustration).
# Same rules as above: durable, general, no statistics, accurate for the US and Canada.
MYTHS = {
    "card": [
        ("Paying the minimum keeps you on track.",
         "It keeps the account in good standing, but most of the payment goes to interest, so the balance can take "
         "years to shrink. Paying a fixed amount above the minimum is what actually gets you out.", "credit_card"),
        ("Carrying a small balance helps your credit score.",
         "Paying your statement balance in full is what builds a good history. Carrying a balance doesn't help the "
         "score, and it costs you interest.", "warning"),
        ("You can't do anything about a wrong charge.",
         "Card issuers have formal dispute processes for billing errors. Acting quickly, in writing, with your "
         "receipts, matters a lot.", "paycheck"),
    ],
    "loan": [
        ("A lower monthly payment means a cheaper loan.",
         "A longer term can shrink the payment while making the total cost much bigger. Compare the total cost, not "
         "just the payment.", "scale"),
        ("All lenders offer about the same rate.",
         "Rates and fees can differ a lot between lenders for the same borrower. Getting several quotes is one of "
         "the easiest ways to save.", "bank"),
        ("If money gets tight, it's better to wait and hope.",
         "Lenders usually have more options before an account falls behind than after. Calling early is almost "
         "always better.", "calendar"),
    ],
    "credit_file": [
        ("Credit report errors are rare.",
         "Errors happen more than people think: mixed-up files, old debts shown as unpaid, or accounts opened by "
         "identity thieves.", "warning"),
        ("Checking your own credit report hurts your score.",
         "Looking at your own report is a soft inquiry and doesn't affect your score.", "paycheck"),
        ("Disputing an error is pointless.",
         "Bureaus must investigate disputes. A clear dispute with documents is often the fastest way to fix a "
         "wrong entry.", "shield"),
    ],
    "scam": [
        ("Scams only fool careless people.",
         "Scams are designed by professionals to create urgency and trust. Smart, careful people get targeted every "
         "day. Slowing down is the best defense.", "warning"),
        ("If caller ID shows my bank, it's my bank.",
         "Caller ID and logos can be faked. Hang up and call the number on your card or the official website.",
         "shield"),
        ("Once you've paid a scammer, nothing can be done.",
         "Acting fast matters. Tell your bank immediately and report it. Some payments can be stopped or "
         "recovered, especially when you move quickly.", "bank"),
    ],
    "grow": [
        ("You need a lot of money to start investing.",
         "Time matters more than the starting amount. Small, regular contributions started early can grow into "
         "real money.", "growth_arrow"),
        ("Saving is only for people with high incomes.",
         "A set amount moved automatically on payday works at almost any income. The habit matters more than the "
         "amount.", "piggy_bank"),
        ("An emergency fund is wasted money.",
         "A cash cushion keeps a surprise bill from turning into high-interest debt, which protects your progress.",
         "shield"),
    ],
    "invest": [
        ("A one percent fee is too small to matter.",
         "It's charged every year on your whole balance, so over decades it can take a large share of your "
         "growth.", "warning"),
        ("Picking winning stocks is the way to grow wealth.",
         "Most investors, and many professionals, struggle to beat the market consistently. Broad, low-cost funds "
         "spread the risk.", "growth_arrow"),
        ("When the market drops, you should get out.",
         "Selling after big drops often means locking in losses and missing the recovery. Match your risk to when "
         "you'll need the money.", "scale"),
    ],
    "bank": [
        ("All my money is protected, whatever the amount.",
         "Deposit insurance has limits and rules by account type, through the FDIC in the US and CDIC in Canada. "
         "Know where your coverage ends.", "shield"),
        ("Bank fees are unavoidable.",
         "Many fees can be avoided by meeting simple account rules or switching accounts. Ask your bank.", "bank"),
        ("A payment app works just like a bank account.",
         "Payments sent to the wrong person can be very hard to reverse. Double-check every recipient.", "warning"),
    ],
    "generic": [
        ("Good money habits take a lot of willpower.",
         "The best habits are automatic. Decide once, then let automation do the work.", "calendar"),
        ("Asking for help with money is a sign of failure.",
         "Many banks, lenders and nonprofit credit counselors offer free guidance. Asking early saves money.",
         "lightbulb"),
    ],
}
