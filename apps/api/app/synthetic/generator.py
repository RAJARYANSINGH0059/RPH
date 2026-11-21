"""Deterministic synthetic cybercrime case generator.

Order of operations (blueprint §10.2): TRUTH -> clean artefacts -> chaos corruption -> (caller) ingest via public pipeline.

Everything is fictional: `.test` domains, RFC 5737 documentation IPs, fictional banks, fictional VPAs with the
`@fictbank` / `@testpay` handles, and a SYNTHETIC DATA watermark in every artefact.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

GENERATOR_VERSION = "0.3.0"
SCENARIO_VERSION = "1"

SCENARIOS = ["phishing_to_mule", "fake_customer_care", "fake_loan_job", "investment_scam", "qr_marketplace", "multi_victim_network"]
DIFFICULTIES = ["clean", "messy", "high_noise", "adversarial"]
SIZES = {"small": (2, 3, 1), "medium": (4, 6, 2), "large": (8, 12, 4)}  # victims, mule accounts, exits
SIZE_LIMITS = {"small": 60, "medium": 250, "large": 900}  # max transactions (safe upper bound)

FIRST = ["Aarav", "Vihaan", "Diya", "Ananya", "Kabir", "Ishaan", "Meera", "Riya", "Arjun", "Saanvi", "Rohan", "Priya", "Dev", "Nisha", "Karan", "Tara"]
LAST = ["Sharma", "Verma", "Singh", "Gupta", "Jain", "Mehta", "Patel", "Yadav", "Chauhan", "Rathore", "Bhatt", "Kaur"]
BANKS = ["FICTBANK", "TESTPAY BANK", "DEMO COOP BANK", "SAMPLE FINANCE"]
HANDLES = ["fictbank", "testpay"]
PROVIDERS = [("SampleCloud CDN", 64500, True), ("DemoHost VPS", 64501, False), ("TestNet Shared Hosting", 64502, True), ("Fictional Dedicated", 64503, False)]
DOC_IP_PREFIXES = ["192.0.2.", "198.51.100.", "203.0.113."]

SCENARIO_TEXT = {
    "phishing_to_mule": ("received an SMS claiming my bank KYC would expire and clicked the link", "KYC update portal"),
    "fake_customer_care": ("searched for a customer care number online and the person asked me to install a screen sharing app", "customer support refund"),
    "fake_loan_job": ("was promised an instant loan / job and asked to pay a processing fee", "loan processing fee"),
    "investment_scam": ("joined a trading group that promised guaranteed daily returns", "investment deposit"),
    "qr_marketplace": ("tried to sell an item on a marketplace and the buyer sent a QR code to 'receive' payment", "marketplace QR payment"),
    "multi_victim_network": ("received a call about a parcel held by customs and was told to pay a release fee", "customs release fee"),
}


@dataclass
class Account:
    acct_no: str
    holder: str
    bank: str
    vpa: str
    role: str  # victim|mule_l1|mule_l2|exit|unrelated
    opening_balance_minor: int


@dataclass
class Tx:
    ref: str
    when: datetime
    src: Account
    dst: Account
    amount_minor: int
    channel: str
    narration: str
    hop: int
    path_id: int


@dataclass
class Truth:
    accounts: list[Account]
    transactions: list[Tx]
    paths: list[dict]
    domains: list[dict]  # {domain, role: campaign|decoy, ip, provider, asn, valid_from, valid_to, is_cdn}
    true_edges: list[dict]
    false_edges: list[dict]  # relationships that MUST NOT be asserted (decoys)
    mule_accounts: list[str]
    params: dict
    chaos: list[dict] = field(default_factory=list)


class Generator:
    def __init__(self, scenario_type: str, difficulty: str, size: str, seed: int):
        assert scenario_type in SCENARIOS, scenario_type
        assert difficulty in DIFFICULTIES, difficulty
        assert size in SIZES, size
        self.scenario_type, self.difficulty, self.size, self.seed = scenario_type, difficulty, size, seed
        self.rng = random.Random(f"{scenario_type}|{difficulty}|{size}|{seed}|{SCENARIO_VERSION}")
        self.t0 = datetime(2026, 3, 2, 9, 0, tzinfo=timezone.utc) + timedelta(days=self.rng.randint(0, 120))

    # ----- helpers
    def _name(self) -> str:
        return f"{self.rng.choice(FIRST)} {self.rng.choice(LAST)}"

    def _acct(self, role: str, holder: str | None = None) -> Account:
        holder = holder or self._name()
        bank = self.rng.choice(BANKS)
        no = "".join(str(self.rng.randint(0, 9)) for _ in range(12))
        vpa = f"{holder.split()[0].lower()}{self.rng.randint(10, 99)}@{self.rng.choice(HANDLES)}"
        bal = self.rng.randint(5_000, 250_000) * 100
        return Account(no, holder, bank, vpa, role, bal)

    def _ref(self) -> str:
        return "SYN" + "".join(self.rng.choice("0123456789ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(12))

    def _ip(self) -> str:
        return self.rng.choice(DOC_IP_PREFIXES) + str(self.rng.randint(10, 250))

    # ----- truth
    def build_truth(self) -> Truth:
        n_victims, n_mules, n_exits = SIZES[self.size]
        if self.scenario_type == "multi_victim_network":
            n_victims += 2
        victims = [self._acct("victim") for _ in range(n_victims)]
        l1 = [self._acct("mule_l1") for _ in range(max(1, n_mules // 2))]
        l2 = [self._acct("mule_l2") for _ in range(max(1, n_mules - len(l1)))]
        exits = [self._acct("exit") for _ in range(n_exits)]
        unrelated = [self._acct("unrelated") for _ in range(2 + (2 if self.difficulty in {"high_noise", "adversarial"} else 0))]
        accounts = victims + l1 + l2 + exits + unrelated

        txs: list[Tx] = []
        paths: list[dict] = []
        topic = SCENARIO_TEXT[self.scenario_type][1]
        limit = SIZE_LIMITS[self.size]
        for pid, v in enumerate(victims):
            amount = self.rng.randint(80, 4_900) * 100 if self.scenario_type != "investment_scam" else self.rng.randint(5_000, 95_000) * 100
            t = self.t0 + timedelta(days=self.rng.randint(0, 20), hours=self.rng.randint(0, 12), minutes=self.rng.randint(0, 59))
            m1 = l1[pid % len(l1)]
            r1 = self._ref()
            txs.append(Tx(r1, t, v, m1, amount, "UPI", f"UPI/{r1}/{m1.vpa}/{topic}", 1, pid))
            # hop 2: within 0.5–30 hours, possibly split
            t2 = t + timedelta(hours=self.rng.uniform(0.5, 30))
            m2 = l2[pid % len(l2)]
            if self.rng.random() < 0.3 and len(l2) > 1:
                a1 = amount // 2
                r2a, r2b = self._ref(), self._ref()
                m2b = l2[(pid + 1) % len(l2)]
                txs.append(Tx(r2a, t2, m1, m2, a1, "IMPS", f"IMPS/{r2a}/{m2.holder.upper()}", 2, pid))
                txs.append(Tx(r2b, t2 + timedelta(minutes=self.rng.randint(1, 40)), m1, m2b, amount - a1, "IMPS", f"IMPS/{r2b}/{m2b.holder.upper()}", 2, pid))
                second = [(m2, a1), (m2b, amount - a1)]
            else:
                r2 = self._ref()
                txs.append(Tx(r2, t2, m1, m2, amount, "IMPS", f"IMPS/{r2}/{m2.holder.upper()}", 2, pid))
                second = [(m2, amount)]
            chain_accounts = [v.acct_no, m1.acct_no]
            for (mm, amt) in second:
                t3 = t2 + timedelta(hours=self.rng.uniform(0.2, 20))
                ex = exits[pid % len(exits)]
                r3 = self._ref()
                txs.append(Tx(r3, t3, mm, ex, amt - (amt % 100 if self.rng.random() < 0.2 else 0), "NEFT" if self.rng.random() < 0.5 else "CASH",
                              f"NEFT/{r3}/{ex.holder.upper()}" if True else "ATM CASH WDL", 3, pid))
                chain_accounts += [mm.acct_no, ex.acct_no]
            paths.append({"path_id": pid, "victim": v.acct_no, "accounts": chain_accounts, "amount_minor": amount, "hops": 3})
        # background noise transactions for mules/unrelated (salary, groceries)
        noise_n = min(limit - len(txs), 6 + 4 * len(accounts) if self.difficulty != "clean" else 4)
        for _ in range(max(0, noise_n)):
            a = self.rng.choice(accounts)
            b = self.rng.choice(unrelated)  # background payments go to unrelated merchants/people only
            if a is b:
                continue
            r = self._ref()
            tw = self.t0 + timedelta(days=self.rng.randint(-10, 30), hours=self.rng.randint(0, 23))
            txs.append(Tx(r, tw, a, b, self.rng.randint(50, 2500) * 100, self.rng.choice(["UPI", "CARD", "NEFT"]), f"{self.rng.choice(['GROCERY', 'RENT', 'SALARY', 'MOBILE RECHARGE'])}/{r}", 0, -1))
        txs.sort(key=lambda x: x.when)

        # infrastructure truth: campaign domains + decoys sharing CDN IP + stale DNS
        domains = []
        cdn = [p for p in PROVIDERS if p[2]][0]
        shared_ip = self._ip()
        camp_domain = f"{self.rng.choice(['secure', 'kyc', 'refund', 'support', 'invest', 'parcel'])}-{self.rng.choice(['update', 'portal', 'care', 'desk', 'pay'])}{self.rng.randint(10, 99)}.test"
        camp_ip = self._ip() if self.difficulty == "clean" else shared_ip
        prov = self.rng.choice(PROVIDERS) if self.difficulty == "clean" else cdn
        domains.append({"domain": camp_domain, "role": "campaign", "ip": camp_ip, "provider": prov[0], "asn": prov[1], "is_cdn": prov[2],
                        "valid_from": (self.t0 - timedelta(days=5)).isoformat(), "valid_to": (self.t0 + timedelta(days=25)).isoformat()})
        n_decoys = {"clean": 0, "messy": 1, "high_noise": 2, "adversarial": 3}[self.difficulty]
        for i in range(n_decoys):
            d = f"{self.rng.choice(['bakery', 'school', 'news', 'cricket', 'recipes', 'temple'])}-{self.rng.choice(['jaipur', 'udaipur', 'kota', 'ajmer'])}{self.rng.randint(1, 99)}.test"
            domains.append({"domain": d, "role": "decoy", "ip": shared_ip, "provider": cdn[0], "asn": cdn[1], "is_cdn": True,
                            "valid_from": (self.t0 - timedelta(days=400)).isoformat(), "valid_to": None})
        if self.difficulty in {"high_noise", "adversarial"}:
            domains.append({"domain": camp_domain, "role": "campaign_stale", "ip": self._ip(), "provider": PROVIDERS[1][0], "asn": PROVIDERS[1][1], "is_cdn": False,
                            "valid_from": (self.t0 - timedelta(days=300)).isoformat(), "valid_to": (self.t0 - timedelta(days=200)).isoformat()})
        mules = [a.acct_no for a in l1 + l2 + exits]
        true_edges = [{"type": "TRANSFERRED_TO", "src": t.src.acct_no, "dst": t.dst.acct_no, "ref": t.ref, "amount_minor": t.amount_minor} for t in txs if t.hop > 0]
        true_edges.append({"type": "USES_PAYMENT_IDENTIFIER", "src": camp_domain, "dst": l1[0].vpa})
        false_edges = [{"type": "COMMON_OPERATOR", "src": camp_domain, "dst": d["domain"], "reason": "shared_cdn_ip_only"} for d in domains if d["role"] == "decoy"]
        return Truth(accounts, txs, paths, domains, true_edges, false_edges, mules,
                     {"scenario_type": self.scenario_type, "difficulty": self.difficulty, "size": self.size, "seed": self.seed,
                      "scenario_version": SCENARIO_VERSION, "generator_version": GENERATOR_VERSION, "t0": self.t0.isoformat(),
                      "campaign_domain": camp_domain, "campaign_vpa": l1[0].vpa, "victims": [v.acct_no for v in victims]})

    # ----- chaos
    def chaos_level(self) -> dict:
        return {"clean": dict(missing=0.0, ambig=0.0, ocr=0.0, dup=0.0, drift=False, balance=False, similar=False),
                "messy": dict(missing=0.05, ambig=0.15, ocr=0.0, dup=0.04, drift=True, balance=True, similar=False),
                "high_noise": dict(missing=0.12, ambig=0.3, ocr=0.08, dup=0.08, drift=True, balance=True, similar=True),
                "adversarial": dict(missing=0.12, ambig=0.3, ocr=0.1, dup=0.08, drift=True, balance=True, similar=True)}[self.difficulty]
