"""Shared output contract applied only to the image-provider request.

Keep stored questionnaire specifications intact: accepting an existing result
compares those specifications with the user's current answers.
"""

IMAGE_OUTPUT_CONTRACT = (
    "AUROOM IMAGE OUTPUT CONTRACT:\n"
    "Return a clean architectural image only. Do not render any text, letters, "
    "digits, numbers, pseudo-text, gibberish, captions, labels, legends, signs, "
    "logos, signatures, watermarks, UI elements or technical annotations. "
    "Do not draw dimension lines, measurement arrows, rulers, scale bars, "
    "coordinate grids, callouts, area labels or dimension values. "
    "All numerical measurements, quantities and sizes in the brief are geometry "
    "constraints only: respect their scale and proportions without printing them "
    "on the image. Do not copy text or annotations from reference images. "
    "If the brief asks for visible writing or markings, follow this text-free "
    "output contract instead. Check the final image for any writing before returning it."
)


def build_image_output_prompt(prompt: str) -> str:
    return f"{prompt}\n\n{IMAGE_OUTPUT_CONTRACT}"
