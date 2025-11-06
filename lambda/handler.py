"""
Alexa Skill Lambda Handler

This Lambda function integrates with the FastAPI middleware to handle
asynchronous LLM requests from Alexa, working around the 8-second timeout.

Flow:
1. User asks Alexa a question
2. Lambda creates job via API, returns "thinking..."
3. Alexa stays in session and auto-reprompts
4. Lambda polls API until job completes
5. Returns final answer to user
"""

import os
import json
import logging
import requests
from typing import Dict, Any, Optional

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# API configuration
API_BASE_URL = os.environ.get('API_BASE_URL', 'http://your-api-url.com')
API_TIMEOUT = 3  # Quick timeout for API calls
MAX_POLLING_RETRIES = 6  # ~30-40 seconds max wait time

# Feedback messages for progressive updates
FEEDBACK_MESSAGES = [
    "Let me think about that...",
    "Still working on it...",
    "Almost there...",
    "Just a moment more...",
    "This is taking a bit longer than usual...",
]


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler for Alexa Skill requests.

    Handles:
    - LaunchRequest: Initial skill invocation
    - IntentRequest: User intents (questions, commands)
    - SessionEndedRequest: Session cleanup
    """
    try:
        logger.info(f"Received event: {json.dumps(event)}")

        request_type = event['request']['type']

        if request_type == 'LaunchRequest':
            return handle_launch(event)
        elif request_type == 'IntentRequest':
            return handle_intent(event)
        elif request_type == 'SessionEndedRequest':
            return handle_session_ended(event)
        else:
            logger.warning(f"Unknown request type: {request_type}")
            return build_response("I'm not sure how to handle that.")

    except Exception as e:
        logger.error(f"Error handling request: {str(e)}", exc_info=True)
        return build_response(
            "Sorry, I encountered an error. Please try again.",
            should_end_session=True
        )


def handle_launch(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle LaunchRequest - skill opened without specific intent"""
    speech = (
        "Welcome to Jarvis. You can ask me questions and I'll use "
        "advanced AI to provide detailed answers. What would you like to know?"
    )
    return build_response(
        speech,
        should_end_session=False,
        session_attributes={}
    )


def handle_intent(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle IntentRequest - process user intents"""
    intent_name = event['request']['intent']['name']
    session = event['session'].get('attributes', {})

    # Handle built-in intents
    if intent_name in ['AMAZON.CancelIntent', 'AMAZON.StopIntent']:
        return handle_cancel(session)
    elif intent_name == 'AMAZON.HelpIntent':
        return handle_help()

    # If we have an active job, check its status (polling)
    # This handles the case where Alexa re-prompts or user says something during wait
    elif 'job_id' in session:
        # If it's a new question intent, handle as new question
        # Otherwise, treat as polling request
        if intent_name == 'AskQuestionIntent':
            # Cancel old job and start new one
            old_job_id = session.get('job_id')
            if old_job_id:
                try:
                    requests.delete(
                        f"{API_BASE_URL}/job/{old_job_id}",
                        timeout=API_TIMEOUT
                    )
                    logger.info(f"Cancelled old job {old_job_id}")
                except Exception as e:
                    logger.error(f"Error cancelling old job: {str(e)}")
            return handle_question(event)
        else:
            # Any other intent while job is running = poll
            return handle_polling(event)

    # Handle new question intent
    elif intent_name == 'AskQuestionIntent':
        return handle_question(event)

    else:
        return build_response(
            "I didn't understand that. Please ask me a question.",
            should_end_session=False
        )


def handle_question(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle initial question from user.
    Creates a job via the API and returns immediately.
    """
    try:
        # Extract question from intent
        question = extract_question(event)
        if not question:
            return build_response(
                "I didn't catch your question. Please try again.",
                should_end_session=False
            )

        session_id = event['session']['sessionId']

        logger.info(f"Creating job for question: {question[:100]}...")

        # Call API to create job
        response = requests.post(
            f"{API_BASE_URL}/ask",
            json={
                "question": question,
                "session_id": session_id,
                "provider": "anthropic",  # Can be made configurable
                "max_tokens": 1024
            },
            timeout=API_TIMEOUT
        )

        if response.status_code != 200:
            logger.error(f"API error: {response.status_code} - {response.text}")
            return build_response(
                "Sorry, I'm having trouble processing your request right now.",
                should_end_session=True
            )

        job_data = response.json()
        job_id = job_data['job_id']

        logger.info(f"Job created: {job_id}")

        # Return "thinking" response and keep session open
        return build_response(
            FEEDBACK_MESSAGES[0],
            should_end_session=False,
            session_attributes={
                'job_id': job_id,
                'retries': 0,
                'question': question
            }
        )

    except requests.Timeout:
        logger.error("API timeout when creating job")
        return build_response(
            "Sorry, the service is taking too long to respond.",
            should_end_session=True
        )
    except Exception as e:
        logger.error(f"Error creating job: {str(e)}", exc_info=True)
        return build_response(
            "Sorry, I encountered an error processing your question.",
            should_end_session=True
        )


def handle_polling(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle polling requests - check if job is complete.
    This is triggered by Alexa's auto-reprompt after silence.
    """
    session = event['session'].get('attributes', {})
    job_id = session.get('job_id')
    retries = session.get('retries', 0)

    logger.info(f"Polling job {job_id}, retry {retries}")

    try:
        # Check job status
        response = requests.get(
            f"{API_BASE_URL}/status/{job_id}",
            timeout=API_TIMEOUT
        )

        if response.status_code != 200:
            logger.error(f"API error checking status: {response.status_code}")
            return build_response(
                "Sorry, I lost track of your request. Please ask again.",
                should_end_session=True
            )

        status_data = response.json()
        status = status_data['status']

        logger.info(f"Job {job_id} status: {status}")

        # Job complete - return result
        if status == 'complete':
            result = status_data.get('result', '')

            # Truncate if too long for Alexa (max ~8000 chars for speech)
            if len(result) > 500:
                result = result[:500] + "... That's the key information."

            return build_response(
                result,
                should_end_session=True
            )

        # Job failed - return error
        elif status == 'failed':
            error = status_data.get('error', 'Unknown error')
            logger.error(f"Job failed: {error}")
            return build_response(
                "Sorry, I couldn't process your question. Please try again.",
                should_end_session=True
            )

        # Still processing - continue polling
        elif status in ['pending', 'processing']:
            # Check if we've exceeded max retries
            if retries >= MAX_POLLING_RETRIES:
                logger.warning(f"Max retries exceeded for job {job_id}")
                return build_response(
                    "This is taking longer than expected. Please try asking again in a moment.",
                    should_end_session=True
                )

            # Get appropriate feedback message
            message_index = min(retries, len(FEEDBACK_MESSAGES) - 1)
            feedback = FEEDBACK_MESSAGES[message_index]

            # Return silence/brief feedback and keep polling
            # Using SSML break for brief silence
            speech = f"<speak>{feedback} <break time='2s'/></speak>"

            return build_response(
                speech,
                should_end_session=False,
                session_attributes={
                    'job_id': job_id,
                    'retries': retries + 1,
                    'question': session.get('question')
                },
                use_ssml=True
            )

        else:
            # Unknown status
            logger.error(f"Unknown job status: {status}")
            return build_response(
                "Sorry, something went wrong. Please try again.",
                should_end_session=True
            )

    except requests.Timeout:
        logger.error("API timeout when polling")
        # Continue polling on timeout
        return build_response(
            "<speak><break time='2s'/></speak>",
            should_end_session=False,
            session_attributes={
                'job_id': job_id,
                'retries': retries + 1,
                'question': session.get('question')
            },
            use_ssml=True
        )
    except Exception as e:
        logger.error(f"Error polling job: {str(e)}", exc_info=True)
        return build_response(
            "Sorry, I encountered an error. Please try again.",
            should_end_session=True
        )


def handle_cancel(session: Dict[str, Any]) -> Dict[str, Any]:
    """Handle cancel/stop intent - cleanup job if active"""
    job_id = session.get('job_id')

    if job_id:
        try:
            # Cancel the job
            requests.delete(
                f"{API_BASE_URL}/job/{job_id}",
                timeout=API_TIMEOUT
            )
            logger.info(f"Cancelled job {job_id}")
        except Exception as e:
            logger.error(f"Error cancelling job: {str(e)}")

    return build_response(
        "Okay, cancelled.",
        should_end_session=True
    )


def handle_help() -> Dict[str, Any]:
    """Handle help intent"""
    speech = (
        "You can ask me questions and I'll provide detailed answers "
        "using advanced AI. For example, you can say: "
        "Alexa, ask Jarvis to explain quantum computing. "
        "What would you like to know?"
    )
    return build_response(
        speech,
        should_end_session=False
    )


def handle_session_ended(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle SessionEndedRequest - cleanup"""
    reason = event['request'].get('reason')
    logger.info(f"Session ended: {reason}")

    # Could cleanup jobs here if needed

    return build_response("", should_end_session=True)


def extract_question(event: Dict[str, Any]) -> Optional[str]:
    """Extract question from intent slots or raw text"""
    try:
        intent = event['request']['intent']
        slots = intent.get('slots', {})

        # Try to get question from slot (check both lowercase and uppercase)
        if 'question' in slots and slots['question'].get('value'):
            return slots['question']['value']
        elif 'Question' in slots and slots['Question'].get('value'):
            return slots['Question']['value']

        # Fallback: try to reconstruct from raw text
        # This depends on your Alexa Skill configuration
        return None

    except Exception as e:
        logger.error(f"Error extracting question: {str(e)}")
        return None


def build_response(
    speech_text: str,
    should_end_session: bool = True,
    session_attributes: Optional[Dict[str, Any]] = None,
    use_ssml: bool = False
) -> Dict[str, Any]:
    """
    Build Alexa response object.

    Args:
        speech_text: Text for Alexa to speak
        should_end_session: Whether to end the session
        session_attributes: Session data to persist
        use_ssml: Whether speech_text contains SSML markup

    Returns:
        Alexa response dictionary
    """
    if session_attributes is None:
        session_attributes = {}

    response = {
        "version": "1.0",
        "sessionAttributes": session_attributes,
        "response": {
            "outputSpeech": {
                "type": "SSML" if use_ssml else "PlainText",
            },
            "shouldEndSession": should_end_session
        }
    }

    # Add speech text in correct format
    if use_ssml:
        # Ensure SSML is wrapped in speak tags
        if not speech_text.startswith('<speak>'):
            speech_text = f"<speak>{speech_text}</speak>"
        response["response"]["outputSpeech"]["ssml"] = speech_text
    else:
        response["response"]["outputSpeech"]["text"] = speech_text

    return response
