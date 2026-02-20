import re
from collections import Counter

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
except Exception:
    TfidfVectorizer = None
    LogisticRegression = None

# temporary in-memory training dataset (we will replace with real data later)
train_texts = [
    "accused granted bail due to lack of evidence",
    "petition dismissed and appeal rejected",
    "court allowed compensation to petitioner",
    "criminal charges proved beyond doubt",
    "benefit of doubt given to accused",
    "case dismissed for insufficient proof"
]

train_labels = [1, 0, 1, 0, 1, 0]   # 1 = success, 0 = fail

vectorizer = None
model = None
if TfidfVectorizer is not None and LogisticRegression is not None:
    vectorizer = TfidfVectorizer()
    X = vectorizer.fit_transform(train_texts)

    model = LogisticRegression()
    model.fit(X, train_labels)


def predict_case(text: str):
    clean = (text or "").lower()
    if vectorizer is None or model is None:
        positive_hits = len(re.findall(r"\b(granted|allowed|benefit|compensation|acquitted)\b", clean))
        negative_hits = len(re.findall(r"\b(dismissed|rejected|proved|convicted|insufficient)\b", clean))
        score = max(0.01, min(0.99, 0.5 + (positive_hits - negative_hits) * 0.12))
        prob = score
    else:
        vec = vectorizer.transform([clean])
        prob = model.predict_proba(vec)[0][1]

    prediction = "Likely to Win" if prob > 0.5 else "Likely to Lose"

    return {
        "prediction": prediction,
        "confidence": float(prob),
        "important_factors": [
            "Keyword polarity from legal outcome terms",
            "Baseline text classification probability",
        ],
    }


def predict_case_with_history(text: str):
    """
    Uses existing judged/predicted cases as weak supervision.
    Falls back to baseline predictor when historical data is sparse.
    """
    base = predict_case(text)
    try:
        from backend.database.mongo import get_db

        db = get_db()
        rows = list(db["case_predictions"].find({}, {"case_number": 1, "prediction": 1, "confidence": 1}).limit(1500))
        if len(rows) < 20:
            return base

        token_re = re.compile(r"[a-zA-Z]{3,}")
        q_tokens = set(token_re.findall((text or "").lower()))
        if not q_tokens:
            return base

        samples = []
        for row in rows:
            case_number = row.get("case_number")
            pred = row.get("prediction")
            if not case_number or not pred:
                continue
            case_doc = db["raw_judgments"].find_one({"case_number": case_number}, {"judgment_text.clean_text": 1, "judgment_text.raw_text": 1})
            if not case_doc:
                continue
            ctext = case_doc.get("judgment_text", {}).get("clean_text") or case_doc.get("judgment_text", {}).get("raw_text") or ""
            if not ctext:
                continue
            c_tokens = set(token_re.findall(ctext.lower()[:4000]))
            if not c_tokens:
                continue
            inter = len(q_tokens & c_tokens)
            if inter == 0:
                continue
            union = len(q_tokens | c_tokens)
            sim = inter / max(1, union)
            samples.append((sim, pred, float(row.get("confidence", 0.5))))

        if len(samples) < 5:
            return base

        top = sorted(samples, key=lambda x: x[0], reverse=True)[:25]
        label_scores = Counter()
        for sim, pred, conf in top:
            label_scores[pred] += sim * (0.5 + conf / 2.0)

        if not label_scores:
            return base

        best_label, best_score = label_scores.most_common(1)[0]
        total_score = sum(label_scores.values()) or 1.0
        hist_conf = min(0.95, max(0.5, best_score / total_score))

        if best_label != base["prediction"]:
            combined_conf = (hist_conf + base["confidence"]) / 2.0
            return {
                "prediction": best_label,
                "confidence": float(combined_conf),
                "source": "historical+baseline",
                "important_factors": [
                    "Past similar judgment outcomes",
                    "Token overlap similarity with historical cases",
                    "Baseline classifier score",
                ],
            }

        return {
            "prediction": best_label,
            "confidence": float(max(hist_conf, base["confidence"])),
            "source": "historical+baseline",
            "important_factors": [
                "Past similar judgment outcomes",
                "Token overlap similarity with historical cases",
                "Baseline classifier score",
            ],
        }
    except Exception:
        return base
