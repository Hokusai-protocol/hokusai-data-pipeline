"""Example DSPy program for email generation.

This demonstrates how to create a DSPy program that can be loaded
by the Hokusai DSPy Model Loader.
"""

from typing import Optional

import dspy


class EmailSignature(dspy.Signature):
    """Signature for email generation."""

    recipient: str = dspy.InputField(desc="Email recipient name")
    subject: str = dspy.InputField(desc="Email subject line")
    context: str = dspy.InputField(desc="Context or main points to cover")
    tone: Optional[str] = dspy.InputField(
        desc="Desired tone (formal, casual, etc.)", default="professional"
    )

    email_body: str = dspy.OutputField(desc="Generated email body")


class CritiqueSignature(dspy.Signature):
    """Signature for email critique."""

    email_text: str = dspy.InputField(desc="Email text to critique")
    criteria: str = dspy.InputField(desc="Criteria for evaluation")

    critique: str = dspy.OutputField(desc="Detailed critique")
    suggestions: str = dspy.OutputField(desc="Improvement suggestions")
    score: float = dspy.OutputField(desc="Quality score from 0-10")


class ReviseSignature(dspy.Signature):
    """Signature for email revision."""

    original_email: str = dspy.InputField(desc="Original email text")
    critique: str = dspy.InputField(desc="Critique feedback")
    suggestions: str = dspy.InputField(desc="Specific suggestions")

    revised_email: str = dspy.OutputField(desc="Improved email text")


class EmailAssistant(dspy.Module):
    """DSPy program for comprehensive email assistance.

    This program can:
    1. Generate emails from context
    2. Critique existing emails
    3. Revise emails based on feedback
    """

    def __init__(self) -> None:
        super().__init__()

        # Initialize the LM (would be configured externally in production)
        self.lm = dspy.OpenAI(model="gpt-4", temperature=0.7)
        dspy.settings.configure(lm=self.lm)

        # Create predictors for each signature
        self.email_generator = dspy.Predict(EmailSignature)
        self.email_critic = dspy.Predict(CritiqueSignature)
        self.email_reviser = dspy.Predict(ReviseSignature)

    def forward(
        self,
        recipient: str,
        subject: str,
        context: str,
        tone: str = "professional",
        improve: bool = True,
    ):
        """Generate and optionally improve an email.

        Args:
            recipient: Name of email recipient
            subject: Email subject line
            context: Context or main points
            tone: Desired tone
            improve: Whether to run improvement cycle

        Returns:
            dict: Contains final_email and optionally critique/suggestions

        """
        # Generate initial email
        initial_result = self.email_generator(
            recipient=recipient, subject=subject, context=context, tone=tone
        )

        if not improve:
            return {"final_email": initial_result.email_body, "iterations": 0}

        # Critique the email
        critique_result = self.email_critic(
            email_text=initial_result.email_body,
            criteria="clarity, professionalism, completeness, engagement",
        )

        # If score is already high, return as is
        if critique_result.score >= 8.0:
            return {
                "final_email": initial_result.email_body,
                "critique": critique_result.critique,
                "score": critique_result.score,
                "iterations": 0,
            }

        # Otherwise, revise based on feedback
        revision_result = self.email_reviser(
            original_email=initial_result.email_body,
            critique=critique_result.critique,
            suggestions=critique_result.suggestions,
        )

        return {
            "final_email": revision_result.revised_email,
            "initial_email": initial_result.email_body,
            "critique": critique_result.critique,
            "suggestions": critique_result.suggestions,
            "score": critique_result.score,
            "iterations": 1,
        }

    def generate_email(self, **kwargs):
        """Convenience method for just generating an email."""
        kwargs["improve"] = False
        result = self.forward(**kwargs)
        return result["final_email"]

    def critique_email(self, email_text: str, criteria: str = None):
        """Convenience method for critiquing an existing email."""
        if criteria is None:
            criteria = "clarity, professionalism, completeness, engagement"

        result = self.email_critic(email_text=email_text, criteria=criteria)

        return {
            "critique": result.critique,
            "suggestions": result.suggestions,
            "score": result.score,
        }

    def revise_email(self, email_text: str, feedback: str):
        """Convenience method for revising an email based on feedback."""
        # First critique to get structured feedback
        critique_result = self.critique_email(email_text)

        # Then revise
        result = self.email_reviser(
            original_email=email_text,
            critique=critique_result["critique"],
            suggestions=feedback or critique_result["suggestions"],
        )

        return result.revised_email


# Example usage function (not part of the class)
def example_usage() -> None:
    """Demonstrate how to use the EmailAssistant."""
    assistant = EmailAssistant()

    # Generate a follow-up email
    result = assistant.forward(
        recipient="Sarah Johnson",
        subject="Project Update Meeting Follow-up",
        context=(
            "Discussed Q4 roadmap, need to confirm timeline for feature X, "
            "budget concerns raised"
        ),
        tone="professional",
        improve=True,
    )

    print("Final Email:")
    print(result["final_email"])

    if "critique" in result:
        print(f"\nQuality Score: {result['score']}/10")
        print(f"Critique: {result['critique']}")


if __name__ == "__main__":
    # Only run example if executed directly
    example_usage()
