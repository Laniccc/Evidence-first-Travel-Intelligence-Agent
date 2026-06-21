from app.schemas.review import PersonaImplication, ReviewAspect, ReviewAspectName


class PersonaImplicationGenerator:
    PERSONAS = ["elderly", "family_with_children", "couple", "photographer", "budget_traveler", "first_timer"]

    def generate(self, aspects: list[ReviewAspect], profile: dict) -> list[PersonaImplication]:
        implications: list[PersonaImplication] = []
        party = [p.lower() if isinstance(p, str) else getattr(p, "value", str(p)).lower() for p in profile.get("party", [])]

        walk = self._find(aspects, ReviewAspectName.WALKING_INTENSITY)
        crowd = self._find(aspects, ReviewAspectName.CROWD_LEVEL)
        photo = self._find(aspects, ReviewAspectName.PHOTO_EXPERIENCE)
        value = self._find(aspects, ReviewAspectName.VALUE_FOR_MONEY)

        fit, reason = "moderate", "Cultural value is high but slopes/crowds may be challenging."
        if walk and walk.sentiment == "negative":
            fit = "poor" if walk.severity == "high" else "moderate"
            reason = "Reviews indicate uphill walking and fatigue risk for seniors."
        implications.append(PersonaImplication(persona="elderly", fit=fit, reason=reason))

        family_fit = "moderate" if crowd and crowd.sentiment == "negative" else "good"
        implications.append(
            PersonaImplication(
                persona="family_with_children",
                fit=family_fit,
                reason="Family-friendly if queues and walking are managed.",
            )
        )

        implications.append(
            PersonaImplication(persona="couple", fit="good", reason="Scenic and photogenic, best at quieter hours.")
        )

        photo_fit = "good" if photo and photo.sentiment != "negative" else "moderate"
        implications.append(
            PersonaImplication(
                persona="photographer",
                fit=photo_fit,
                reason="Photo spots are a common review theme." if photo else "Scenic landmark with photo potential.",
            )
        )

        budget_fit = "moderate" if value and value.sentiment == "negative" else "good"
        implications.append(
            PersonaImplication(
                persona="budget_traveler",
                fit=budget_fit,
                reason="Some reviews mention value concerns." if value and value.sentiment == "negative" else "Reasonable value for a landmark visit.",
            )
        )

        implications.append(
            PersonaImplication(persona="first_timer", fit="good", reason="Strong cultural landmark value for first visits.")
        )
        return implications

    @staticmethod
    def _find(aspects: list[ReviewAspect], name: ReviewAspectName) -> ReviewAspect | None:
        return next((a for a in aspects if a.aspect == name), None)
