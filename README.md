# regoatnitionbot
Proof of concept Telegram bot for AWS Rekognition tagging of images

## You'll need:
* An AWS API key
* A Telegram bot API key
* A Python runtime environment
* Probably some other stuff, too

## To use
* Create an AWS account and an IAM user that has "Describe Labels" and "Moderate Images" access to the Rekognition service. This accout will be billed for usage of the API, but casual usage won't exceed AWS Free Tier limits.
* Install the AWS Boto3 library per the instructions at https://aws.amazon.com/sdk-for-python/
* Generate a .aws/config file with your AWS API key per the instructions above
* Register a Telegram bot using the instructions here: https://core.telegram.org/bots
* Write the API key into a file called .telegramconfig in the working directory of the script

## Optional
* Use Telegram's botfather to disable privacy mode. This will allow the bot to analyze all images (sent by humans) in a chat, not just images privately messaged to it.

## To run
Takes no arguments. Just run
`rekog.py`
And send messages to the bot on Telegram. `/help` is available interactively in the bot.
