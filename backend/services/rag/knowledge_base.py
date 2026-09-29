"""
Seed medical-reference corpus for the RAG knowledge base.

Short, general-education explainers for the biomarkers already scored in
services/population_stats.py. These are general reference material, not
diagnostic advice — the Q&A endpoint prompt reinforces that framing before
these chunks ever reach the LLM.
"""
from __future__ import annotations

from typing import Any, Dict, List

KNOWLEDGE_BASE: List[Dict[str, Any]] = [
    {
        "id": "hemoglobin",
        "title": "Hemoglobin",
        "text": (
            "Hemoglobin is the oxygen-carrying protein in red blood cells. Low hemoglobin "
            "(anemia) commonly results from iron, vitamin B12, or folate deficiency, chronic "
            "blood loss, kidney disease, or bone marrow disorders, and often presents with "
            "fatigue, pallor, or shortness of breath. High hemoglobin can result from dehydration, "
            "smoking, living at high altitude, or polycythemia vera."
        ),
    },
    {
        "id": "hematocrit",
        "title": "Hematocrit",
        "text": (
            "Hematocrit is the percentage of blood volume made up of red blood cells and tracks "
            "closely with hemoglobin. Low hematocrit suggests anemia or overhydration; high "
            "hematocrit suggests dehydration, chronic hypoxia (e.g. lung disease, smoking), or a "
            "bone-marrow overproduction disorder."
        ),
    },
    {
        "id": "white blood cells",
        "title": "White Blood Cell Count (WBC)",
        "text": (
            "White blood cells are the immune system's front line. An elevated WBC count "
            "(leukocytosis) often reflects an active infection, inflammation, stress response, or "
            "steroid use, and less commonly a blood cancer. A low count (leukopenia) can result "
            "from viral infections, certain medications (including chemotherapy), autoimmune "
            "disease, or bone marrow suppression, and raises infection risk."
        ),
    },
    {
        "id": "platelets",
        "title": "Platelets",
        "text": (
            "Platelets are cell fragments responsible for clotting. Low platelets (thrombocytopenia) "
            "can result from viral infection, autoimmune destruction, liver disease, certain drugs, "
            "or bone marrow disorders, and raises bleeding/bruising risk. High platelets "
            "(thrombocytosis) can follow inflammation, infection, iron deficiency, or a bone marrow "
            "disorder, and can raise clotting risk."
        ),
    },
    {
        "id": "total cholesterol",
        "title": "Total Cholesterol",
        "text": (
            "Total cholesterol sums LDL, HDL, and a fraction of triglycerides. It's a screening "
            "number, not a diagnosis — the breakdown between LDL and HDL matters more than the "
            "total. Elevated total cholesterol is influenced by diet, genetics (e.g. familial "
            "hypercholesterolemia), sedentary lifestyle, and some medical conditions like "
            "hypothyroidism."
        ),
    },
    {
        "id": "ldl cholesterol",
        "title": "LDL Cholesterol",
        "text": (
            "LDL ('bad') cholesterol carries cholesterol into artery walls and is the primary "
            "modifiable driver of atherosclerosis and cardiovascular disease risk. It's typically "
            "lowered through diet (reducing saturated fat), exercise, weight loss, or statin/other "
            "lipid-lowering therapy when risk is elevated."
        ),
    },
    {
        "id": "hdl cholesterol",
        "title": "HDL Cholesterol",
        "text": (
            "HDL ('good') cholesterol helps clear excess cholesterol from the bloodstream back to "
            "the liver. Higher HDL is generally protective against cardiovascular disease; low HDL "
            "is associated with smoking, obesity, sedentary lifestyle, type 2 diabetes, and certain "
            "medications."
        ),
    },
    {
        "id": "triglycerides",
        "title": "Triglycerides",
        "text": (
            "Triglycerides are the main form of stored fat measured in blood, strongly influenced "
            "by recent food intake, alcohol, and refined-carbohydrate intake. Chronically elevated "
            "triglycerides are linked to metabolic syndrome, type 2 diabetes, and (at very high "
            "levels) pancreatitis risk."
        ),
    },
    {
        "id": "glucose",
        "title": "Fasting Glucose",
        "text": (
            "Fasting glucose reflects blood sugar after roughly 8 hours without food. Elevated "
            "fasting glucose is the core marker for prediabetes and diabetes; low values "
            "(hypoglycemia) can result from fasting, certain medications (especially insulin or "
            "sulfonylureas), or, less commonly, hormonal or liver disorders."
        ),
    },
    {
        "id": "hba1c",
        "title": "Hemoglobin A1c (HbA1c)",
        "text": (
            "HbA1c reflects average blood glucose over roughly the past 2-3 months, making it a "
            "longer-term marker than a single fasting glucose reading. It's the standard marker "
            "used to diagnose and monitor diabetes and prediabetes, and is less affected by "
            "short-term factors like a recent meal."
        ),
    },
    {
        "id": "creatinine",
        "title": "Creatinine",
        "text": (
            "Creatinine is a muscle-metabolism waste product filtered out by the kidneys, making it "
            "a core marker of kidney function. Elevated creatinine suggests reduced kidney "
            "filtration (acute or chronic kidney disease, dehydration, or urinary obstruction); it "
            "also varies naturally with muscle mass."
        ),
    },
    {
        "id": "bun",
        "title": "Blood Urea Nitrogen (BUN)",
        "text": (
            "BUN measures urea, another waste product cleared by the kidneys, and is usually read "
            "alongside creatinine. Elevated BUN can reflect reduced kidney function, dehydration, "
            "high protein intake, or gastrointestinal bleeding; low BUN can reflect liver disease "
            "or malnutrition."
        ),
    },
    {
        "id": "egfr",
        "title": "Estimated Glomerular Filtration Rate (eGFR)",
        "text": (
            "eGFR estimates how well the kidneys filter blood, calculated from creatinine plus age, "
            "sex, and sometimes race. It's the primary staging marker for chronic kidney disease — "
            "lower eGFR indicates reduced kidney function, with values below roughly 60 sustained "
            "over three months indicating CKD."
        ),
    },
    {
        "id": "alt",
        "title": "ALT (Alanine Aminotransferase)",
        "text": (
            "ALT is an enzyme concentrated in the liver; it leaks into the blood when liver cells "
            "are damaged. Elevated ALT is a sensitive marker for liver injury from causes including "
            "fatty liver disease, alcohol use, viral hepatitis, and certain medications."
        ),
    },
    {
        "id": "ast",
        "title": "AST (Aspartate Aminotransferase)",
        "text": (
            "AST is present in the liver but also heart and skeletal muscle, so it's less "
            "liver-specific than ALT. It's usually interpreted alongside ALT: an AST/ALT ratio "
            "above 2 is a classic (though not definitive) pattern seen in alcohol-related liver "
            "injury."
        ),
    },
    {
        "id": "bilirubin",
        "title": "Total Bilirubin",
        "text": (
            "Bilirubin is a breakdown product of red blood cells, cleared by the liver into bile. "
            "Elevated bilirubin causes jaundice and can indicate liver dysfunction, bile duct "
            "obstruction, or increased red blood cell breakdown (hemolysis)."
        ),
    },
    {
        "id": "albumin",
        "title": "Albumin",
        "text": (
            "Albumin is the main protein made by the liver and reflects both liver synthetic "
            "function and nutritional status. Low albumin can result from chronic liver disease, "
            "malnutrition, kidney protein loss (nephrotic syndrome), or chronic inflammation."
        ),
    },
    {
        "id": "sodium",
        "title": "Sodium",
        "text": (
            "Sodium is the main electrolyte governing fluid balance. Low sodium (hyponatremia) is "
            "most often driven by excess fluid retention (heart failure, kidney disease, certain "
            "medications) or fluid loss with inadequate salt intake; high sodium usually reflects "
            "dehydration or, rarely, excess salt/mineralocorticoid activity."
        ),
    },
    {
        "id": "potassium",
        "title": "Potassium",
        "text": (
            "Potassium is critical for heart and muscle electrical activity, so abnormal values are "
            "watched closely. Low potassium can follow diuretic use, vomiting/diarrhea, or "
            "inadequate intake; high potassium can follow kidney dysfunction, certain medications "
            "(e.g. ACE inhibitors), or tissue breakdown."
        ),
    },
    {
        "id": "calcium",
        "title": "Calcium",
        "text": (
            "Calcium supports bone structure, muscle contraction, and nerve signaling, and is "
            "tightly regulated by parathyroid hormone and vitamin D. High calcium is often linked "
            "to hyperparathyroidism or certain cancers; low calcium can result from vitamin D "
            "deficiency, kidney disease, or low parathyroid hormone."
        ),
    },
    {
        "id": "tsh",
        "title": "TSH (Thyroid Stimulating Hormone)",
        "text": (
            "TSH is released by the pituitary to regulate thyroid hormone production, and is the "
            "primary screening test for thyroid function. Elevated TSH usually indicates an "
            "underactive thyroid (hypothyroidism); low TSH usually indicates an overactive thyroid "
            "(hyperthyroidism)."
        ),
    },
    {
        "id": "vitamin d",
        "title": "Vitamin D (25-OH)",
        "text": (
            "25-hydroxyvitamin D is the standard marker of vitamin D status, important for calcium "
            "regulation and bone health. Low vitamin D is common and is linked to limited sun "
            "exposure, certain diets, malabsorption, obesity, and darker skin pigmentation in "
            "lower-UV climates."
        ),
    },
    {
        "id": "uric acid",
        "title": "Uric Acid",
        "text": (
            "Uric acid is a purine metabolism byproduct cleared by the kidneys. Elevated uric acid "
            "is the underlying driver of gout (joint inflammation from urate crystal deposition) "
            "and kidney stones, and is influenced by diet (red meat, alcohol, fructose), obesity, "
            "and reduced kidney clearance."
        ),
    },
    {
        "id": "iron",
        "title": "Serum Iron",
        "text": (
            "Serum iron measures iron circulating in blood, usually interpreted alongside ferritin "
            "and transferrin saturation for a fuller picture. Low iron is a common cause of anemia "
            "(from diet, blood loss, or malabsorption); high iron can reflect excess supplementation "
            "or hereditary hemochromatosis."
        ),
    },
]
