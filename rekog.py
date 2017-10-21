#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Andrew Villeneuve 2017
Telegram Bot which uses AWS Rekognition to attempt to label real world
objects in photographs.
Based in part on python-telegram-bot and boto3 sample code.
"""

from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
import logging
import boto3
import os

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

# Default configuration values until overridden
default_config = {'label': 'True',
                  'porn': 'False', 
                  'threshold': '50', 
                  'limit': '4', 
                  'pause': 'False',
                  'last_image': 'None',
                  'celebrity': 'True'}

# Useful for debugging
keep_local_images = False

# If True, images will be stored in a designated S3 bucket for processing.
# If False, images will be uploaded seperately for each API call.
use_s3 = True
bucket = 'regoatnition-images-east'

# If True, per-chat settings will be stored in the provided DynamoDB table
# If False, they will be stored on locally on disk in the provided folder
use_dynamo = False
dynamo_table = "regoatnition-settings"
local_settings_folder = "rekogbot_settings"

#Convienent test data, but we won't use it live
testimg={
    'S3Object': {
        'Bucket': 'andrewmv-sandbox',
        'Name': 'DSC09809.JPG'
    }
}

def repeat(bot, update):
    lastimage = setting(update.message.chat.id, 'last_image')
    if lastimage == 'None':
        update.message.reply_text("No previous image available to repeat")
    else:
        label_image(bot, update, image=lastimage, filename=lastimage)

def label_image(bot, update, image=None, filename=None):
    threshold = float(setting(update.message.chat.id, 'threshold'))

    # Check if we were provided with already-uploaded image id
    if image==None:
        filename = download_image(bot, update)
        image = get_image(bot, update, filename)

        # Do nothing else if we're paused
        if setting(update.message.chat.id, 'pause') == 'True':
            return 0
    else:
        if use_s3:
            image = {
                'S3Object': {
                    'Bucket': bucket,
                    'Name': filename
                }
            }
        else:
            image = get_image(bot, update, filename)

    reply_text = u''
    if setting(update.message.chat.id, 'porn') == 'True':
        reply_text += find_porn(bot, update, image, filename)

    if setting(update.message.chat.id, 'celebrity') == 'True':
        reply_text += find_celebrities(bot, update, image, filename)

    if setting(update.message.chat.id, 'label') == 'True':
        reply_text += find_labels(bot, update, image, filename)

    if reply_text:
        update.message.reply_text(reply_text)
    else:
        update.message.reply_text("No tags found with {} % certainty".format(threshold))

# Download the image in the message to local storage, return the name
def download_image(bot, update):
    file_id = update.message.photo[-1].file_id
    new_file = bot.get_file(file_id)
    filename = str(update.message.chat.id) + "-" + str(update.message.message_id)
    path = "img/" + filename
    new_file.download(custom_path=path)    
    setting(update.message.chat.id, 'last_image', filename)
    return filename

# Get image as a binary blob or S3 reference
# Which one is determined by the use_s3 setting
def get_image(bot, update, filename):
    if use_s3:
        # Put file in S3
        path = 'img/' + filename
        s3 = boto3.resource('s3')
        s3.meta.client.upload_file(path, bucket, filename)
        img = {
            'S3Object': {
                'Bucket': bucket,
                'Name': filename
            }
        }
    else:
        # Read file into memory
        with open(path, 'rb') as f:
            data = f.read()
        img = {
            'Bytes': data
        }
    if not keep_local_images:
        os.remove(path)
    return img

def find_porn(bot, update, image, filename):
    text = u''
    threshold = float(setting(update.message.chat.id, 'threshold'))
    logger.info("Porn tagging image {} using threshold {}".format(filename, threshold))
    try:
        response = rekog.detect_moderation_labels(Image=image, MinConfidence=threshold)
        for thing in response['ModerationLabels']:
            if thing['Name'] == 'Explicit Nudity':
                text += "Porn - {:.2f}%confidence\n".format(thing['Confidence'])
    except Exception as e:
        errstr = "Porn tagging failed with error: {}".format(e)
        logger.error(errstr)
        update.message.reply_text(errstr)
    return text

def find_labels(bot, update, image, filename):
    text = ''
    threshold = float(setting(update.message.chat.id, 'threshold'))
    logger.info("Label tagging image {} using threshold {}".format(filename, threshold))
    try:
        response = rekog.detect_labels(Image=image, MinConfidence=threshold)
        tag_count = 0
        tag_limit = int(setting(update.message.chat.id, 'limit'))
        for thing in response['Labels']:
            if tag_count >= tag_limit:
                break
            text += "{} - {:.2f}% confidence\n".format(thing['Name'], thing['Confidence'])
            tag_count += 1
    except Exception as e:
        errstr = "Label tagging failed with error: {}".format(e)
        logger.error(errstr)
        update.message.reply_text(errstr)
    return text

def find_celebrities(bot, update, image, filename):
    text = u''
    logger.info("Celebrity tagging image {}".format(filename))
    try:
        response = rekog.recognize_celebrities(Image=image)
        tag_count = 0
        tag_limit = int(setting(update.message.chat.id, 'limit'))
        for face in response['CelebrityFaces']:
            if tag_count >= tag_limit:
                break
            text += u'{} - {:.2f}% confidence\n'.format(face['Name'], face['Face']['Confidence'])
            tag_count += 1
    except Exception as e:
        errstr = "Celebrity tagging failed with error: {}".format(e)
        logger.error(errstr)
        update.message.reply_text(errstr)
    return text

# Define a few command handlers. These usually take the two arguments bot and
# update. Error handlers also receive the raised TelegramError object in error.
def start(bot, update):
    help(bot, update)

def help(bot, update):
    update.message.reply_text("""Send me an image - I'll tell you what I find in it\n
    /labels [on|off] to toggle label detection\n
    /porn [on|off] to toggle porn detection\n
    /threshold [0-100] to set label detection confidence threshold""")

def error(bot, update, error):
    logger.warn('Update "%s" caused error "%s"' % (update, error))

def stop(bot, update):
    update.message.reply_text('Goodbye')
    bot.leave_chat(chat_id=update.message.chat.id)

def label_setting(bot, update):
    setting_toggler(update, name='label')

def porn_setting(bot, update):
    setting_toggler(update, name='porn')

def pause_setting(bot, update):
    setting_toggler(update, name='pause')

def celeb_setting(bot, update):
    setting_toggler(update, name='celebrity')

def list_settings(bot, update):
    text = ""
    for key in default_config:
        text += key
        text += " : "
        text += setting(update.message.chat.id, key)
        text += "\n"
    update.message.reply_text(text)

def setting_toggler(update, name):
    chat = update.message.chat.id
    verb = "enabled" 
    if 'on' in update.message.text.lower():
        setting(chat, name, True)
    elif 'off' in update.message.text.lower():
        setting(chat, name, False)
        verb = "disabled"
    else:
    #Toggle if no explicit setting
        if setting(chat, name) == 'True':
            setting(chat, name, False)
            verb = "disabled"
        else:
            setting(chat, name, True)
    update.message.reply_text('{} detection {} for images in this chat'.format(name, verb))

def threshold_setting(bot, update):
    text = update.message.text.split()
    try:
        newvalue = int(text[1])
    except IndexError:
        update.message.reply_text("Current threshold is {}".format(setting(update.message.chat.id, 'threshold')))
        return 
    except ValueError:
        update.message.reply_text("Detection threshold must be 0 - 100")
        return
    if newvalue >= 0 and newvalue <= 100:
        setting(update.message.chat.id, 'threshold', newvalue)
        update.message.reply_text("Detection threshold set to {} % for this chat".format(newvalue))
    else:
        update.message.reply_text("Detection threshold must be 0 - 100")

def limit_setting(bot, update):
    text = update.message.text.split()
    try:
        newvalue = int(text[1])
    except IndexError:
        update.message.reply_text("Current limit is {}".format(setting(update.message.chat.id, 'limit')))
        return
    except ValueError:
        update.message.reply_text("Limit must be a number")
        return
    setting(update.message.chat.id, 'limit', newvalue)
    update.message.reply_text("Tag limit set to {} for this chat".format(newvalue))

# Get or set per-chat settings
def setting(chat, name, newvalue=None):
    if use_dynamo:
        return setting_in_dynamo(chat, name, newvalue)
    else:
        return setting_on_disk(chat, name, newvalue)

def setting_in_dynamo(chat, name, newvalue=None):
    if newvalue==None:
        return get_from_dynamo(chat, name)
    else:
        put_in_dynamo(chat, name, newvalue)

def put_in_dynamo(chat, name, newvalue):
    dynamo_client = boto3.client('dynamodb')
    query = {
        'TableName' : dynamo_table, 
        'Item' : {
            'chat_id' : {
                'N' : str(chat)
            },
            name : {
                'S' : str(newvalue)
            }
        }
    }
    dynamo_client.put_item(**query)

def get_from_dynamo(chat, name):
    dynamo_client = boto3.client('dynamodb')
    query = {
        'TableName' : dynamo_table,
        'Key' : {
            'chat_id' : {
                'N' : str(chat)
            },
         },
         'ConsistentRead' : True,
         'AttributesToGet' : [name]
    }
    try:
        response = dynamo_client.get_item(**query)
        return response['Item'][name]['S']
    except KeyError as e:
        return default_config[name]
        
def setting_on_disk(chat, name, newvalue=None):
    filename = local_settings_folder + "/{}".format(chat)
    config = default_config.copy()
    try:
        with open(filename, 'r') as f:
            for line in f:
                try:
                    key, value = line.split(':', 2)
                    config[key] = value.rstrip()
                except ValueError as e:
                    logger.warn("malformatted settings file - {} - {} on line {}".format(filename, e, line))
    except IOError as e:
        logger.warn("No settings saved for chat {}, using defaults".format(chat))
    if newvalue==None:
        return config[name]
    else:
        config[name] = newvalue
        with open(filename, 'w') as f:
            for key in config.keys():
                f.write("{}:{}\n".format(key, config[key]))

def main():
    # Create the AWS client
    global rekog
    rekog = boto3.client('rekognition')

    # Create the Telegram EventHandler and pass it our token
    apikey = ''
    try:
        with open('.telegramconfig', 'r') as f:
            apikey = f.readline().rstrip()
    except IOError as e:
        logger.error("No Telegram API key found in .telegramconfig")
        return 1
    updater = Updater(apikey)

    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    # on different commands - answer in Telegram
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help))
    dp.add_handler(CommandHandler("stop", stop))

    # options commands
    dp.add_handler(CommandHandler("labels", label_setting))
    dp.add_handler(CommandHandler("threshold", threshold_setting))
    dp.add_handler(CommandHandler("porn", porn_setting))
    dp.add_handler(CommandHandler("celeb", celeb_setting))
    dp.add_handler(CommandHandler("celebrity", celeb_setting))
    dp.add_handler(CommandHandler("limit", limit_setting))
    dp.add_handler(CommandHandler("pause", pause_setting))
    dp.add_handler(CommandHandler("settings", list_settings))
    dp.add_handler(CommandHandler("repeat", repeat))
    dp.add_handler(CommandHandler("go", repeat))

    # on picture message, run the Rekognition workflow
    dp.add_handler(MessageHandler(Filters.photo, label_image))

    # log all errors
    dp.add_error_handler(error)

    # Start the Bot
    updater.start_polling()

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()


if __name__ == '__main__':
    main()
