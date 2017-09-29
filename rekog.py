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

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

#Convienent test data, but we won't use it live
testimg={
    'S3Object': {
        'Bucket': 'andrewmv-sandbox',
        'Name': 'DSC09809.JPG'
    }
}

def label_image(bot, update):
    # Download the image
    file_id = update.message.photo[-1].file_id
    new_file = bot.get_file(file_id)
    path = "img/" + str(update.message.chat.id) + "-" + str(update.message.message_id)
    new_file.download(custom_path=path)    #Save image to disc
    with open(path, 'rb') as f:            #Read back off of disc
        data = f.read()
    img = {
        'Bytes': data
    }

    # Get the reply string ready
    text = ''

    threshold = float(setting(update.message.chat.id, 'threshold'))

    if setting(update.message.chat.id, 'porn') == 'True':
    # Porn tagging
        logger.info("Porn tagging image {} using threshold {}".format(path, threshold))
        try:
            response = rekog.detect_moderation_labels(Image=img, MinConfidence=threshold)
        except Exception as e:
            errstr = "Porn tagging failed with error {}".format(e)
            logger.error(errstr)
            update.message.reply_text(errstr)
        for thing in response['ModerationLabels']:
            if thing['Name'] == 'Explicit Nudity':
                text += "Porn - {:.2f}%confidence\n".format(thing['Confidence'])

    if setting(update.message.chat.id, 'label') == 'True':
    # Label tagging
        logger.info("Label tagging image {} using threshold {}".format(path, threshold))
        try:
            response = rekog.detect_labels(Image=img, MinConfidence=threshold)
        except Exception as e:
            errstr = "Label tagging failed with error {}".format(e)
            logger.error(errstr)
            update.message.reply_text(errstr)
        #TODO - use S3 to skip the second upload
        tag_count = 0
        tag_limit = int(setting(update.message.chat.id, 'limit'))
        for thing in response['Labels']:
            if tag_count >= tag_limit:
                break
            text += "{} - {:.2f}% confidence\n".format(thing['Name'], thing['Confidence'])
            tag_count += 1

    if text:
        update.message.reply_text(text)
    else:
        update.message.reply_text("No tags found with {} % certainty".format(threshold))

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

#Look up per chat settings, and save them to a file
def setting(chat, name, newvalue=None):
    config = {'label': 'True', 'porn': 'False', 'threshold': '50', 'limit': '4'}
    filename = "rekogbot_settings/{}".format(chat)
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
    dp.add_handler(CommandHandler("limit", limit_setting))

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
