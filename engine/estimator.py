"""Prototype comparable-property engine. Python 3.10+; standard library only."""
import json
from numbers import Real
from pathlib import Path
from statistics import median

WEIGHTS = {"land_m2": .25, "construction_m2": .25, "bedrooms": .15,
           "bathrooms": .15, "parking_spaces": .10, "floors": .05}
QUALITY_WEIGHT = .05


def _valid_value(value):
    """Return whether a comparable numeric value is a positive real number."""
    return isinstance(value, Real) and not isinstance(value, bool) and value > 0

def load_dataset(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def unique_candidates(properties):
    """Conservatively remove only manually reviewed probable duplicate groups."""
    seen, out = set(), []
    for p in properties:
        group = p.get("duplicate_group")
        if group:
            if group in seen:
                continue
            seen.add(group)
        out.append(p)
    return out

def field_similarity(target, candidate, field):
    a, b = target.get(field), candidate.get(field)
    if a is None or b is None:
        return None
    if not _valid_value(a) or not _valid_value(b):
        return None
    if field in ("land_m2", "construction_m2"):
        if a <= 0 or b <= 0:
            return None
        # 1.0 for equal; declines smoothly with relative difference.
        return max(0.0, 1.0 - abs(a-b) / max(a, b))
    # For count fields, exact match 1; each count difference reduces similarity.
    return max(0.0, 1.0 - abs(a-b) / max(1, a, b))

def score_property(target, candidate):
    weighted, comparable_weight, known = 0.0, 0.0, 0
    details, field_reasons = {}, {}
    for field, weight in WEIGHTS.items():
        sim = field_similarity(target, candidate, field)
        details[field] = sim
        target_value, candidate_value = target.get(field), candidate.get(field)
        if sim is not None:
            weighted += sim * weight
            comparable_weight += weight
            known += 1
            field_reasons[field] = "compared"
        elif target_value is None or candidate_value is None:
            field_reasons[field] = "missing"
        elif not _valid_value(target_value):
            field_reasons[field] = "invalid_target"
        else:
            field_reasons[field] = "invalid_candidate"
    if comparable_weight == 0:
        return {"score": None, "details": details, "field_reasons": field_reasons,
                "known_fields": 0, "coverage": 0.0}
    # Missing fields add no agreement and reduce coverage; they are never matches.
    total_possible_weight = sum(WEIGHTS.values())
    coverage = comparable_weight / total_possible_weight
    agreement = weighted / comparable_weight
    score = 100 * agreement * coverage
    return {"score": round(score, 1), "details": details, "field_reasons": field_reasons,
            "known_fields": known, "coverage": round(coverage, 3),
            "agreement_score": round(100 * agreement, 1)}


def _price_review_reasons(property_, lower_bound, upper_bound):
    reasons = [note for note in property_.get("quality_notes", []) if "price" in note.lower()]
    price = property_.get("price_mxn")
    if _valid_value(price) and lower_bound is not None:
        if price < lower_bound or price > upper_bound:
            reasons.append("Price is outside the dataset IQR review band; it remains included.")
    return reasons


def _price_review_bounds(properties):
    prices = sorted(p.get("price_mxn") for p in properties if _valid_value(p.get("price_mxn")))
    if len(prices) < 4:
        return None, None
    q1 = prices[int((len(prices) - 1) * .25)]
    q3 = prices[int((len(prices) - 1) * .75)]
    iqr = q3 - q1
    return q1 - 1.5 * iqr, q3 + 1.5 * iqr

def estimate(target, properties, min_score=55):
    pool = unique_candidates(properties)
    representative_ids = {p["id"] for p in pool}
    lower_bound, upper_bound = _price_review_bounds(pool)
    scored, candidate_audit, price_review_flags = [], [], []
    for p in pool:
        review_reasons = _price_review_reasons(p, lower_bound, upper_bound)
        if review_reasons:
            price_review_flags.extend(f"{p['id']}: {reason}" for reason in review_reasons)
        if not _valid_value(p.get("price_mxn")):
            candidate_audit.append({"id": p.get("id"), "decision": "excluded",
                                    "reasons": ["invalid_or_missing_price"], "original": p})
            continue
        s = score_property(target, p)
        if s["score"] is not None and s["score"] >= min_score:
            scored.append({**p, "similarity_score": s["score"], "score_details": s["details"],
                           "score_audit": s, "price_review": review_reasons})
            candidate_audit.append({"id": p["id"], "decision": "included",
                                    "reasons": ["meets_minimum_score"], "score_audit": s,
                                    "price_review": review_reasons, "original": p})
        else:
            reason = "no_comparable_valid_fields" if s["score"] is None else "below_minimum_score"
            candidate_audit.append({"id": p["id"], "decision": "excluded", "reasons": [reason],
                                    "score_audit": s, "price_review": review_reasons, "original": p})
    for p in properties:
        if p["id"] not in representative_ids:
            candidate_audit.append({"id": p["id"], "decision": "excluded",
                                    "reasons": ["probable_duplicate_group_represented_once"],
                                    "duplicate_group": p.get("duplicate_group"), "original": p})
    scored.sort(key=lambda x: x["similarity_score"], reverse=True)
    if not scored:
        return {"status":"insufficient_comparables","reference_price_mxn":None,
                "range_mxn":None,"confidence":"low","comparables":[],
                "input_publications_count": len(properties), "unique_properties_count": len(pool),
                "candidate_audit": candidate_audit, "price_review_flags": price_review_flags}
    # Weighted median is more robust than weighted mean and less sensitive to price outliers.
    weighted_prices = sorted((p["price_mxn"], max(.01, p["similarity_score"]/100)) for p in scored)
    total = sum(w for _,w in weighted_prices)
    acc, weighted_med = 0, weighted_prices[-1][0]
    for price, weight in weighted_prices:
        acc += weight
        if acc >= total/2:
            weighted_med = price
            break
    prices = [p["price_mxn"] for p in scored]
    # Descriptive range is P25-P75 of selected asking prices; not a confidence interval.
    prices_sorted = sorted(prices)
    lo = prices_sorted[max(0, int((len(prices_sorted)-1)*.25))]
    hi = prices_sorted[min(len(prices_sorted)-1, int((len(prices_sorted)-1)*.75))]
    avg_score = sum(p["similarity_score"] for p in scored)/len(scored)
    if len(scored) >= 5 and avg_score >= 75:
        confidence = "medium"
    elif len(scored) >= 3 and avg_score >= 65:
        confidence = "low-to-medium"
    else:
        confidence = "low"
    return {"status":"provisional","reference_price_mxn":weighted_med,
            "range_mxn":[lo,hi],"range_note":"Rango descriptivo entre comparables seleccionados; no es intervalo estadístico de confianza.",
            "confidence":confidence,"comparables_count":len(scored),
            "input_publications_count": len(properties), "unique_properties_count": len(pool),
            "candidate_audit":candidate_audit, "price_review_flags":price_review_flags,
            "comparables":[{"id":p["id"],"source":p["source"],"price_mxn":p["price_mxn"],
                            "similarity_score":p["similarity_score"],"url":p["url"],
                            "score_audit":p["score_audit"],"price_review":p["price_review"]} for p in scored]}

if __name__ == "__main__":
    here = Path(__file__).resolve().parents[1]
    ds = load_dataset(here/"data"/"jardines_del_bosque.json")
    target = {"land_m2":120,"construction_m2":90,"bedrooms":2,"bathrooms":1,
              "parking_spaces":1,"floors":1}
    print(json.dumps(estimate(target, ds["properties"]), ensure_ascii=False, indent=2))
