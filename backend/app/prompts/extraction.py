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
  "readable": <true if at least one field can be extracted with high or low \
confidence; false only if image quality prevents extraction of all fields>,
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

Schema rule: Every entry inside "fields" MUST be an object containing exactly
two keys: "value" and "confidence". This applies to string-valued, numeric-valued,
and boolean-valued fields alike. Never return bare strings, bare numbers, bare
booleans, or bare null values within "fields". Before returning the final JSON,
verify that every field under "fields" conforms to this structure.

Confidence rules (apply to every field):
  "high"      — the value is directly visible and clearly readable.
  "low"       — the field appears to exist but text is partially obscured,
                small, in an unusual font, or otherwise ambiguous.
  "not_found" — the field was not observed in the visible portions of the
                provided panel(s). If not all panels were submitted, it may
                appear elsewhere on the container. value MUST be null.

General transcription rule: unless a field-specific rule below overrides it,
string fields must preserve the exact wording, capitalization, punctuation, and
spacing appearing on the label.

Additional extraction rules:
  schema_version        : always the literal string "1.0" — do not change this value.
  beverage_class        : determine from explicit label evidence only. Do not infer
                          from brand recognition, packaging style, or product
                          knowledge. Return null if the class cannot be established
                          from visible text.
  brand_name            : the consumer-facing product brand as displayed on the label.
                          Prefer the product identity presented most prominently to
                          purchasers. Do NOT use producer, bottler, importer, winery,
                          brewery, or distillery names unless they are also clearly
                          functioning as the displayed brand. Entity-type suffixes
                          (Winery, Brewing Co., Distillery, Inc.) are not part of the
                          brand name unless the label presents them as such.
  class_type            : the product class or type designation exactly as printed
                          (e.g., "Straight Bourbon Whiskey", "Blended Scotch Whisky",
                          "Cabernet Sauvignon"). Preserve capitalization and wording.
                          Do not include marketing adjectives unless they form the
                          legal class/type designation.
  abv_pct               : numeric only, no % sign (e.g. 5.2 not "5.2%").
  abv_text              : verbatim ABV text as printed. When ABV text is present,
                          populate both abv_text (verbatim) and abv_pct (the numeric
                          value extracted from that text).
  proof                 : numeric only, no "Proof" word (e.g. 94.0).
  net_contents_metric   : normalize to standard notation with a space before the
                          unit, uppercase metric unit (e.g., "750 mL", "1.5 L").
  net_contents_us       : normalize to standard notation with a space before the
                          unit, lowercase US unit (e.g., "12 fl oz", "1 pt").
  bottler_name          : legal entity name only. Strip role descriptors
                          ("Bottled by", "Produced by", "Imported by", "Brewed by",
                          "Distilled by", etc.).
  bottler_address       : geographic location only (street address, city, state, zip
                          if present). Do NOT include the company name or role
                          descriptors.
  country_of_origin     : extract the geographic origin statement presented as part
                          of the product identity or origin declaration on the label
                          face. Do NOT derive from bottler, producer, importer, or
                          address text unless the label explicitly presents that text
                          as an origin statement. Preserve at whatever specificity
                          appears on the label (e.g., "American", "California",
                          "Lawrenceburg, Kentucky", "France"). When the claim
                          includes introductory phrases ("Product of", "Imported
                          from", "Made in"), extract only the geographic designation:
                          "Product of France" → "France".
  appellation           : for products using a formal appellation or geographic
                          designation as part of classification (primarily wine AVAs),
                          extract that designation exactly as printed (e.g., "Napa
                          Valley", "Sonoma Coast"). Do not populate from bottler
                          addresses or general origin claims unless the label
                          explicitly presents the text as an appellation designation.
                          country_of_origin and appellation are distinct concepts and
                          may both be populated when both are explicitly present.
  gws_present           : true if Government Warning Statement text is observed;
                          false if all visible panel(s) were inspected and no GWS
                          text was observed; null if image quality prevents
                          determination.
  gws_header / gws_body : transcribe verbatim, exactly as printed including
                          punctuation and capitalization. Populate only when the
                          text is identified as belonging to the Government Warning
                          Statement. If a bilingual label shows multiple warning
                          headers, extract the English text only. Do NOT complete
                          from memory if text is cut off — use confidence "low".
  gws_header_bold / gws_body_bold : true only if the text appears visually heavier
                          than the adjacent body text in the same section; false if
                          text weight is comparable to surrounding text; null if
                          image quality prevents determination.
"""
