"""
backend/utils/cnr_decoder.py

Utility to decode Indian Court CNR (Case Number Record) numbers.
CNR format: SS CC NNNNNNN YYYY
"""

STATE_CODES = {
    "MH": "Maharashtra", "DL": "Delhi", "TN": "Tamil Nadu",
    "KA": "Karnataka",   "AP": "Andhra Pradesh", "TS": "Telangana",
    "UP": "Uttar Pradesh","GJ": "Gujarat",       "RJ": "Rajasthan",
    "WB": "West Bengal",  "PB": "Punjab",         "HR": "Haryana",
    "KL": "Kerala",      "BR": "Bihar",          "MP": "Madhya Pradesh",
}

def decode_cnr(cnr: str) -> dict:
    """
    Decodes a 16-character CNR number into its constituent parts.
    """
    cnr = cnr.strip().upper().replace(" ", "")
    if len(cnr) != 16:
        return {"error": "CNR must be 16 characters"}
    
    state_code = cnr[:2]
    court_code = cnr[2:4]
    case_num   = cnr[4:11]
    year       = cnr[12:16]

    return {
        "cnr": cnr,
        "state_code": state_code,
        "state": STATE_CODES.get(state_code, "Unknown"),
        "court_code": court_code,
        "case_number_seq": case_num,
        "filing_year": year,
    }
