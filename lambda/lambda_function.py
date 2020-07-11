# -*- coding: utf-8 -*-

# This is a High Low Guess game Alexa Skill.
# The skill serves as a simple sample on how to use the
# persistence attributes and persistence adapter features in the SDK.
import random
import json
import logging
import os
import boto3

from ask_sdk_core.skill_builder import CustomSkillBuilder
from ask_sdk_core.utils import is_request_type, is_intent_name
from ask_sdk_core.handler_input import HandlerInput

from ask_sdk_model import Response
from ask_sdk_s3.adapter import S3Adapter

SKILL_NAME = 'Incoherent Game'
bucket_name = os.environ.get('S3_PERSISTENCE_BUCKET')
s3_client = boto3.client('s3',
                         region_name=os.environ.get('S3_PERSISTENCE_REGION'),
                         config=boto3.session.Config(signature_version='s3v4',s3={'addressing_style': 'path'}))
s3_adapter = S3Adapter(bucket_name=bucket_name, path_prefix="Media", s3_client=s3_client)
sb = CustomSkillBuilder(persistence_adapter=s3_adapter)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@sb.request_handler(can_handle_func=is_request_type("LaunchRequest"))
def launch_request_handler(handler_input):
    # get access to persistent attributes
    attr = handler_input.attributes_manager.persistent_attributes
    
    # store initial data if this is the first time
    if not attr:
        attr['gamesPlayed'] = 0
        attr['isPlaying'] = False
        
    # refresh the pairings stored in persistent attributes on every launch
    with open("pairings.json") as file:
        attr['pairings'] = json.loads(file.read())

    # set up the session attributes
    handler_input.attributes_manager.session_attributes = attr

    # text for speech and reprompt
    speech = f"Welcome to Incoherent. You have played {attr['gamesPlayed']} times. Would you like to play?"
    reprompt = "Say yes to start the game or no to quit."

    # execute speech
    handler_input.response_builder.speak(speech).ask(reprompt)
    return handler_input.response_builder.response


@sb.request_handler(can_handle_func=is_intent_name("AMAZON.HelpIntent"))
def help_intent_handler(handler_input):
    # text for speech and reprompt
    speech = "Bruh..."
    reprompt = "Guess the gibberish..."

    # execute speech
    handler_input.response_builder.speak(speech).ask(reprompt)
    return handler_input.response_builder.response


@sb.request_handler(
    can_handle_func=lambda input:
        is_intent_name("AMAZON.CancelIntent")(input) or
        is_intent_name("AMAZON.StopIntent")(input))
def cancel_and_stop_intent_handler(handler_input):
    # get reference to session attributes
    session_attr = handler_input.attributes_manager.session_attributes
    
    # stop game and update information
    session_attr["gamesPlayed"] += 1
    session_attr["isPlaying"] = False
    
    # save to persistent attributes
    handler_input.attributes_manager.persistent_attributes = session_attr
    handler_input.attributes_manager.save_persistent_attributes()
    
    # text for speech
    speech = "Thanks for playing!!"

    # execute speech and end session
    handler_input.response_builder.speak(speech).set_should_end_session(True)
    return handler_input.response_builder.response


@sb.request_handler(can_handle_func=is_request_type("SessionEndedRequest"))
def session_ended_request_handler(handler_input):
    # log info for session termination
    logger.info(f"Session ended with reason: {handler_input.request_envelope.request.reason}")
    return handler_input.response_builder.response


def currently_playing(handler_input):
    # get reference to session attributes
    session_attr = handler_input.attributes_manager.session_attributes

    # return if user is currently playing
    return "isPlaying" in session_attr and session_attr["isPlaying"]


@sb.request_handler(can_handle_func=lambda input:
                    not currently_playing(input) and
                    is_intent_name("AMAZON.YesIntent")(input))
def yes_handler(handler_input):
    # get reference to session attributes
    session_attr = handler_input.attributes_manager.session_attributes
    
    # set up gameplay within session
    session_attr['isPlaying'] = True
    session_attr['gibberish'] = random.choice(list(session_attr['pairings'].keys()))

    # text for speech and reprompt
    speech = reprompt = f"{session_attr['gibberish']}"

    # execute speech
    handler_input.response_builder.speak(speech).ask(reprompt)
    return handler_input.response_builder.response


@sb.request_handler(can_handle_func=lambda input:
                    not currently_playing(input) and
                    is_intent_name("AMAZON.NoIntent")(input))
def no_handler(handler_input):
    # get reference to session attributes
    session_attr = handler_input.attributes_manager.session_attributes
    
    # change playing to false
    session_attr['isPlaying'] = False

    # save to persistent attributes
    handler_input.attributes_manager.persistent_attributes = session_attr
    handler_input.attributes_manager.save_persistent_attributes()

    # text for speech
    speech = "Ok. See you next time!!"

    # execute speech
    handler_input.response_builder.speak(speech)
    return handler_input.response_builder.response


@sb.request_handler(can_handle_func=lambda input:
                    currently_playing(input) and
                    is_intent_name("GuessIntent")(input))
def guess_handler(handler_input):
    # get reference to session attributes
    session_attr = handler_input.attributes_manager.session_attributes
    
    # store the answer and the user's guess
    gibberish = session_attr['gibberish']
    answer = session_attr['pairings'][gibberish].lower()
    guess = handler_input.request_envelope.request.intent.slots["guess"].value.lower()

    # game logic
    if guess == 'skip':
        # generate new gibberish
        gibberish = session_attr['gibberish'] = random.choice(list(session_attr['pairings'].keys()))
        answer = session_attr['pairings'][gibberish].lower()
        
        # text for speech and reprompt
        speech = f"Your new gibberish is: {gibberish}"
        reprompt = f"{gibberish}"
    elif guess == answer:
        # generate new gibberish
        gibberish = session_attr['gibberish'] = random.choice(list(session_attr['pairings'].keys()))
        answer = session_attr['pairings'][gibberish].lower()
        
        # text for speech and reprompt
        speech = f"Nice! {guess} was the correct answer! Your new gibberish is: {gibberish}"
        reprompt = f"{gibberish}"
    else:
        # prompt user to guess again
        speech = f"That was wrong. The gibberish is: {gibberish}"
        reprompt = f"{gibberish}"
    
    # execute speech
    handler_input.response_builder.speak(speech).ask(reprompt)
    return handler_input.response_builder.response


@sb.request_handler(can_handle_func=lambda input:
                    is_intent_name("AMAZON.FallbackIntent")(input) or
                    is_intent_name("AMAZON.YesIntent")(input) or
                    is_intent_name("AMAZON.NoIntent")(input))
def fallback_handler(handler_input):
    # get reference to session attributes
    session_attr = handler_input.attributes_manager.session_attributes
    
    # fallback messages
    if "isPlaying" in session_attr and session_attr["isPlaying"]:
        speech = f"The {SKILL_NAME} can't help you with that. Try to guess the gibberish or say stop to quit."
        reprompt = "Try to guess the gibberish or say stop to quit."
    else:
        speech = f"The {SKILL_NAME} can't help you with that. Would you like to play?"
        reprompt = "Say yes to start the game or no to quit."

    handler_input.response_builder.speak(speech).ask(reprompt)
    return handler_input.response_builder.response


@sb.request_handler(can_handle_func=lambda input: True)
def unhandled_intent_handler(handler_input):
    # text for speech
    speech = "Say yes to continue or no to end the game!!"
    
    # execute speech
    handler_input.response_builder.speak(speech).ask(speech)
    return handler_input.response_builder.response


@sb.exception_handler(can_handle_func=lambda i, e: True)
def all_exception_handler(handler_input, exception):
    # error handling
    logger.error(exception, exc_info=True)
    speech = "Sorry, I can't understand that. Please say it again!!"
    handler_input.response_builder.speak(speech).ask(speech)
    return handler_input.response_builder.response


@sb.global_response_interceptor()
def log_response(handler_input, response):
    # response logging
    logger.info(f"Response: {response}")


lambda_handler = sb.lambda_handler()
