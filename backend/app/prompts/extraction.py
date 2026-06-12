SYSTEM = """\
You are an expert at reading alcoholic beverage labels for TTB regulatory \
compliance. Extract the requested fields from the label image and return a \
single JSON object. Do not explain or add commentary — return only the JSON \
object, with no markdown code fences.

Critical accuracy rules:
- Only transcribe text that is visually present and legible in the image.
- Do NOT reproduce text from memory or training data, especially the Government \
Warning Statement. If the GWS text is partially obscured or cut off, use \
confidence "low" — do not complete it from memory.
- Do NOT infer or guess field values. If a field is not clearly visible, use \
"not_found" or "low" confidence as appropriate.
- If you are uncertain whether text you see is the GWS or something else, \
transcribe exactly what is printed and use confidence "low".
"""

USER_TEMPLATE = """\
Extract all fields from this alcoholic beverage label image.{panel_note}

Return a JSON object with this exact structure (no extra keys, no omitted keys):

{{
  "schema_version": "1.0",
  "readable": <true if you can interpret the image, false otherwise>,
  "beverage_class": <"beer" | "spirits" | "wine" | null>,
  "panels_provided": [<list containing "front" and/or "back" based on visible panels>],
  "extraction_model": "{model}",
  "fields": {{
    "brand_name":          {{"value": <string|null>, "confidence": <"high"|"low"|"not_found">}},
    "class_type":          {{"value": <string|null>, "confidence": <"high"|"low"|"not_found">}},
    "abv_pct":             {{"value": <number|null>, "confidence": <"high"|"low"|"not_found">}},
    "abv_text":            {{"value": <string|null>, "confidence": <"high"|"low"|"not_found">}},
    "proof":               {{"value": <number|null>, "confidence": <"high"|"low"|"not_found">}},
    "net_contents_metric": {{"value": <string|null>, "confidence": <"high"|"low"|"not_found">}},
    "net_contents_us":     {{"value": <string|null>, "confidence": <"high"|"low"|"not_found">}},
    "bottler_name":        {{"value": <string|null>, "confidence": <"high"|"low"|"not_found">}},
    "bottler_address":     {{"value": <string|null>, "confidence": <"high"|"low"|"not_found">}},
    "country_of_origin":   {{"value": <string|null>, "confidence": <"high"|"low"|"not_found">}},
    "gws_present":         {{"value": <true|false|null>, "confidence": <"high"|"low"|"not_found">}},
    "gws_header":          {{"value": <string|null>, "confidence": <"high"|"low"|"not_found">}},
    "gws_body":            {{"value": <string|null>, "confidence": <"high"|"low"|"not_found">}},
    "gws_header_bold":     {{"value": <true|false|null>, "confidence": <"high"|"low"|"not_found">}},
    "gws_body_bold":       {{"value": <true|false|null>, "confidence": <"high"|"low"|"not_found">}},
    "sulfite_declaration": {{"value": <string|null>, "confidence": <"high"|"low"|"not_found">}},
    "vintage":             {{"value": <string|null>, "confidence": <"high"|"low"|"not_found">}},
    "appellation":         {{"value": <string|null>, "confidence": <"high"|"low"|"not_found">}}
  }}
}}

Confidence rules (apply to every field):
  "high"      — you can read the value clearly, OR you are certain the field
                is absent from this image (value must be null in that case).
  "low"       — the field appears to exist but text is partially obscured,
                small, in an unusual font, or otherwise ambiguous.
  "not_found" — the field does not appear anywhere in this image.  It may be
                on another panel.  value MUST be null.

Additional extraction rules:
  gws_header / gws_body : transcribe verbatim, exactly as printed including
                          punctuation and capitalization. Do NOT complete
                          from memory if text is cut off — use confidence "low".
  abv_pct               : numeric only, no % sign  (e.g. 5.2 not "5.2%").
  proof                 : numeric only, no "Proof" word  (e.g. 94.0).
  gws_header_bold / gws_body_bold : true if the text visually appears bold,
                          false if it does not, null if you cannot tell.
"""
