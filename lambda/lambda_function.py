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


# -------------------- environment variables -------------------- 


SKILL_NAME = 'Incoherent Game'
bucket_name = os.environ.get('S3_PERSISTENCE_BUCKET')
s3_client = boto3.client('s3',
                         region_name=os.environ.get('S3_PERSISTENCE_REGION'),
                         config=boto3.session.Config(signature_version='s3v4',s3={'addressing_style': 'path'}))
s3_adapter = S3Adapter(bucket_name=bucket_name, path_prefix='Media', s3_client=s3_client)
sb = CustomSkillBuilder(persistence_adapter=s3_adapter)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# -------------------- helper functions -------------------- 


def currently_playing(handler_input):
    session_attr = handler_input.attributes_manager.session_attributes
    return 'isPlaying' in session_attr and session_attr['isPlaying']


def pick_new_gibberish(handler_input):
    session_attr = handler_input.attributes_manager.session_attributes
    if not session_attr['possible']: reshuffle_possible(handler_input)
    return session_attr['possible'].pop()


def reshuffle_possible(handler_input):
    session_attr = handler_input.attributes_manager.session_attributes
    possible = [*session_attr['pairings']]
    random.shuffle(possible)
    session_attr['possible'] = possible


def save_game(handler_input):
    session_attr = handler_input.attributes_manager.session_attributes
    handler_input.attributes_manager.persistent_attributes = session_attr
    handler_input.attributes_manager.save_persistent_attributes()


# -------------------- intent handlers -------------------- 


@sb.request_handler(can_handle_func=is_request_type('LaunchRequest'))
def launch_request_handler(handler_input):
    """ launch game and setup session attributes """
    
    attr = handler_input.attributes_manager.persistent_attributes
    
    if not attr:
        attr['gamesPlayed'] = 0
        attr['isPlaying'] = False
        
    handler_input.attributes_manager.session_attributes = attr
    
    speech = f"Welcome to Incoherent. You have played {attr['gamesPlayed']} times. Would you like to play?"
    reprompt = "Say yes to start the game or no to quit."
    
    handler_input.response_builder.speak(speech).ask(reprompt)
    return handler_input.response_builder.response


@sb.request_handler(can_handle_func=lambda input:
                    not currently_playing(input) and
                    is_intent_name('AMAZON.YesIntent')(input))
def yes_handler(handler_input):
    """ start game if user says yes """
    
    session_attr = handler_input.attributes_manager.session_attributes
    
    with open('pairings.json') as file:
        session_attr['pairings'] = json.loads(file.read())
        session_attr['possible'] = []
    
    session_attr['isPlaying'] = True
    session_attr['gibberish'] = pick_new_gibberish(handler_input)

    speech = f"Your gibberish is: {session_attr['gibberish']}. Say repeat to hear it again or skip if it's too hard."
    reprompt = f"{session_attr['gibberish']}"

    handler_input.response_builder.speak(speech).ask(reprompt)
    return handler_input.response_builder.response


@sb.request_handler(can_handle_func=lambda input:
                    not currently_playing(input) and
                    is_intent_name('AMAZON.NoIntent')(input))
def no_handler(handler_input):
    """ do not start game if user says no """
    
    session_attr = handler_input.attributes_manager.session_attributes
    session_attr['isPlaying'] = False
    save_game(handler_input)

    speech = "Ok. See you next time!!"

    handler_input.response_builder.speak(speech)
    return handler_input.response_builder.response


@sb.request_handler(can_handle_func=lambda input:
                    currently_playing(input) and
                    is_intent_name('GuessIntent')(input))
def guess_handler(handler_input):
    """ game logic """
    
    session_attr = handler_input.attributes_manager.session_attributes
    
    gibberish = session_attr['gibberish']
    answers = session_attr['pairings'][gibberish]
    guess = handler_input.request_envelope.request.intent.slots['guess'].value.lower()

    if guess == 'repeat':
        speech = f"Your gibberish is: {gibberish}"
    elif guess == 'skip':
        gibberish = session_attr['gibberish'] = pick_new_gibberish(handler_input)
        speech = f"Your new gibberish is: {gibberish}"
    elif guess in answers:
        gibberish = session_attr['gibberish'] = pick_new_gibberish(handler_input)
        speech = f"Nice! {guess} was the correct answer! Your new gibberish is: {gibberish}"
    else:
        speech = f"That was wrong. Your gibberish is: {gibberish}"
    reprompt = f"{gibberish}"
    
    handler_input.response_builder.speak(speech).ask(reprompt)
    return handler_input.response_builder.response


@sb.request_handler(can_handle_func=is_intent_name('AMAZON.HelpIntent'))
def help_intent_handler(handler_input):
    """ help instructions and faq """
    
    speech = "Guess the gibberish! Say 'repeat' to hear it again, 'skip' if it's too hard, or 'stop' to quit the game!"
    reprompt = "Say 'repeat' to hear the gibberish again, 'skip' if it's too hard, or 'stop' to quit the game!"

    handler_input.response_builder.speak(speech).ask(reprompt)
    return handler_input.response_builder.response


@sb.request_handler(
    can_handle_func=lambda input:
        is_intent_name('AMAZON.CancelIntent')(input) or
        is_intent_name('AMAZON.StopIntent')(input))
def cancel_and_stop_intent_handler(handler_input):
    """ end game and save data """
    
    session_attr = handler_input.attributes_manager.session_attributes
    session_attr['gamesPlayed'] += 1
    session_attr['isPlaying'] = False
    save_game(handler_input)
    
    speech = "Thanks for playing!!"

    handler_input.response_builder.speak(speech).set_should_end_session(True)
    return handler_input.response_builder.response


@sb.request_handler(can_handle_func=is_request_type('SessionEndedRequest'))
def session_ended_request_handler(handler_input):
    """ logs abrupt endings """
    
    logger.info(f"Session ended with reason: {handler_input.request_envelope.request.reason}")
    return handler_input.response_builder.response


@sb.request_handler(can_handle_func=lambda input:
                    is_intent_name('AMAZON.FallbackIntent')(input) or
                    is_intent_name('AMAZON.YesIntent')(input) or
                    is_intent_name('AMAZON.NoIntent')(input))
def fallback_handler(handler_input):
    """ fallbacks """
    
    session_attr = handler_input.attributes_manager.session_attributes
    
    if 'isPlaying' in session_attr and session_attr['isPlaying']:
        speech = f"The {SKILL_NAME} can't help you with that. Try to guess the gibberish or say skip if it's too hard."
        reprompt = "Try to guess the gibberish or say skip if it's too hard."
    else:
        speech = f"The {SKILL_NAME} can't help you with that. Would you like to play?"
        reprompt = "Say yes to start the game or no to quit."

    handler_input.response_builder.speak(speech).ask(reprompt)
    return handler_input.response_builder.response


@sb.request_handler(can_handle_func=lambda input: True)
def unhandled_intent_handler(handler_input):
    speech = "Sorry, I can't understand that. Please say it again!!"
    handler_input.response_builder.speak(speech).ask(speech)
    return handler_input.response_builder.response


@sb.exception_handler(can_handle_func=lambda i, e: True)
def all_exception_handler(handler_input, exception):
    logger.error(exception, exc_info=True)
    speech = "Sorry, I can't understand that. Please say it again!!"
    handler_input.response_builder.speak(speech).ask(speech)
    return handler_input.response_builder.response


@sb.global_response_interceptor()
def log_response(handler_input, response):
    logger.info(f"Response: {response}")


lambda_handler = sb.lambda_handler()

