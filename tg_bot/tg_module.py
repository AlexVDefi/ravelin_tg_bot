#!/usr/bin/env python3
import telethon
from telethon import TelegramClient, events
from telethon.tl.types import InputStickerSetID, MessageMediaPhoto, Photo, PhotoSize, PhotoSizeEmpty, PhotoSizeProgressive, MessageMediaDocument
from telethon.tl.functions.channels import EditBannedRequest, GetMessagesRequest
from telethon.tl.functions.messages import GetStickerSetRequest
from telethon.tl.types import ChatBannedRights, InputStickerSetID
from telethon.tl.types import ChannelParticipantsKicked, ChannelParticipantsBanned
from telethon.utils import pack_bot_file_id, resolve_bot_file_id
from time import time
import re
import sqlalchemy as db
from alchemysession import AlchemySessionContainer
from telethon.tl.custom import Button
from os.path import dirname as up
import json
import asyncio
import string
import random, os
from captcha.image import ImageCaptcha
import datetime
import pickle
import ravelin_functions as rf

# File paths to other folders
parent_dir = os.path.abspath(up(__file__))
filepath_bin = os.path.join(up(parent_dir), 'binaries')
filepath_sqlite = os.path.join(up(parent_dir), 'SQLite')
filepath_captchas = os.path.join(up(parent_dir), 'captchas')
filepath_files = os.path.join(up(parent_dir), 'files')

# Access the config file
configFile = filepath_bin + "/config.json"
with open(configFile) as f:
    config = json.load(f)

# Access the project file
presets = filepath_bin + "/presets.json"
with open(presets) as f:
    project_presets = json.load(f)

# Set to False for Production, True for Development
if config['DEVELOPMENT_MODE'] == 1:
    dev_bot = True
else:
    dev_bot = False

# START DEV BOT
if dev_bot is True:
    bot_token = config['TG_DEV_BOT_TOKEN']
    sqlite_db = filepath_sqlite + "/tg_bot_dev.db"
    session_db = filepath_sqlite + "/dev_session.sqlite"
    session_name = "dev_session"

# START PROD BOT
else:
    bot_token = config['TG_PROD_BOT_TOKEN']
    sqlite_db = filepath_sqlite + "/tg_bot_prod.db"
    session_db = filepath_sqlite + "/prod_session.sqlite"
    session_name = "prod_session"

# Channel ID - Can be changed in config
channel_id = config['CHANNEL_ID']

# Project specifics taken from project_specs.json file
project_name = project_presets['settings']['project_name']
settings = project_presets['settings']

# Set up connection with SQLite database
metadata = db.MetaData()
engine = db.create_engine(f'sqlite:///{sqlite_db}')
connection = engine.connect()

# Set up connection for the Sessions container that Telethon use
session_engine = db.create_engine(f'sqlite:///{session_db}')
session_connection = session_engine.connect()
container = AlchemySessionContainer(engine=session_connection)
session = container.new_session(session_name)

# Set up the tables from the databases
users_table = db.Table('tg_users', metadata, autoload=True, autoload_with=engine)
channel_table = db.Table('channel_table', metadata, autoload=True, autoload_with=engine)
admin_table = db.Table('admin_table', metadata, autoload=True, autoload_with=engine)
files_table = db.Table('file_refs', metadata, autoload=True, autoload_with=engine)
version_table = db.Table('version', metadata, autoload=True, autoload_with=session_engine)

# Create the bot with the Session container, API ID and API hash.
bot = TelegramClient(session, config['TG_API_ID'], config['TG_API_HASH']).start(bot_token=bot_token)
print("Connected")

# Open admin list text file
with open(filepath_bin+"/admin_list.json") as f:
    admin_list = json.load(f)['admins']

# Open banned words text file
with open(filepath_bin+"/banned_words.json") as f:
    banned_words_l = json.load(f)['words']

# Open allowed links text file
with open(filepath_bin+"/allowed_links.json") as f:
    allowed_links_l = json.load(f)['links']


with open(filepath_bin+"/custom_commands.json") as f:
    custom_commands_dict = json.load(f)
    custom_commands_names = custom_commands_dict.keys()


# --- Repeated messages --- #
admin_buttons = [[Button.inline(f'⚙ Configuration', data=b'open-config')],
                 [Button.inline('🔨 Check Banned Users', data=b'check-banned'), Button.inline('🔇 Check Muted Users', data=b'check-muted')],
                 [Button.inline(f'📝✅ Add Custom Command', data=b'add-custom'), Button.inline(f'📝❌ Remove Custom Command', data=b'remove-custom')],
                 [Button.inline(f'😎✅ Add New Admin', data=b'add-admin'), Button.inline(f'😎❌ Remove Admin', data=b'remove-admin')],
                 [Button.inline(f'🗯✅ Add Banned Word', data=b'add-banned-word'), Button.inline(f'🗯❌ Remove Banned Word', data=b'remove-banned-word')],
                 [Button.inline(f'🌐✅ Add Allowed Link', data=b'add-allowed-links'), Button.inline(f'🌐❌ Remove Allowed Link', data=b'remove-allowed-links')],
                 ]

config_buttons = [[Button.inline(f'⬅ Back to main menu', data=b'open-admin')],
                  [Button.inline(f'💬 Welcome Message:', data=b'toggle-welcome')],
                  [Button.inline(f'🤖 Captcha verification:', data=b'toggle-captcha')],
                  [Button.inline(f'🤬 Banned Words Filter:', data=b'toggle-words')],
                  [Button.inline(f'🔗 Banned Links Filter:', data=b'toggle-links')],
                  [Button.inline(f'📛 Banned Names Filter:', data=b'toggle-names')],
                  [Button.inline(f'📝 Custom Commands Filter:', data=b'toggle-custom')],
                  ]

# Filters for catching words in the chat
help_filter_l = ["/help", "help", "Help"]
banned_links_l = ["https:", "t.me", "http:"]
fun_filter_list = ["bad bot", "stupid bot", "dumb bot", "fuck you bot"]

# --- Filter functions, used by @bot.on decorator --- #
async def custom_filter(event):
    for word in custom_commands_names:
        if "," in word:
            words = str(word).split(", ")
        else:
            words = word
        for new_word in words:
            if new_word.lower() == event.raw_text.lower() or f"{new_word.lower()}@" in event.raw_text.lower():
                return True
            elif new_word+"@" in event.raw_text:
                return True
    return False


async def fun_filter(event):
    for word in fun_filter_list:
        if word.lower() in event.raw_text.lower():
            return True
    return False


async def help_filter(event):
    for word in help_filter_l:
        if word.lower() == event.raw_text.lower():
            return True
    return False


async def edit_admins(event):
    data_match = [b'add-admin', b'remove-admin', b'admin-delete-']
    for entry in data_match:
        if entry in event.data:
            return True
    return False


async def banned_word(event):
    for word in banned_words_l:
        if word.lower() in event.raw_text.lower():
            return True
    return False


async def edit_banned_words(event):
    data_match = [b'add-banned-word', b'remove-banned-word', b'delete-']
    for entry in data_match:
        if entry in event.data:
            return True
    return False


async def banned_links(event):
    for word in banned_links_l:
        if word.lower() in event.raw_text.lower():
            return True
    return False


async def edit_allowed_links(event):
    data_match = [b'add-allowed-link', b'remove-allowed-link', b'link-delete-']
    for entry in data_match:
        if entry in event.data:
            return True
    return False


async def edit_custom_commands(event):
    data_match = [b'add-custom', b'remove-custom', b'custom-delete-']
    for entry in data_match:
        if entry in event.data:
            return True
    return False

async def toggle_settings_func(event):
    if b'toggle-' in event.data:
        return True
    return False

# @bot.on(events.NewMessage(pattern="/price"))
# async def show_price(event):
#     if project_presets['price']['enabled'] == 0:
#         return
#     price_msg = project_presets['price']
#
#     loading_msg = await bot.send_message(event.chat_id, f"⏳ __Loading price...__ ⌛")
#     get_data = df.BlockchainData
#     token_list = []
#     for token in price_msg["tokens"]:
#         token = price_msg["tokens"][str(token)]
#         price = await get_data(token['network'], token['router'], token['address']).get_token_price_in_usdc()
#         line = f"{token['name']}: ${price}\n"
#         token_list.append(line)
#     message_text = price_msg['message']
#     for line in token_list:
#         message_text += line
#     await bot.edit_message(event.chat_id, loading_msg, message_text)


@bot.on(events.NewMessage(pattern="/epoch"))
async def show_epoch(event):
    get_data = rf.BlockchainData
    loading_msg = await bot.send_message(event.chat_id, f"⏳ __Loading Epoch...__ ⌛")
    info_dict = await get_data("MILKOMEDA", "OccamX").get_ravelin_stats()
    message_text = f"⏰ EPOCH ⏰\n" \
                       f"- Current: {info_dict['current_epoch']}\n" \
                       f"- Next in {info_dict['next_epoch']}"
    await bot.edit_message(event.chat_id, loading_msg, message_text)


@bot.on(events.NewMessage(pattern="/price"))
async def show_price(event):
    if project_presets['price']['enabled'] == 0:
        return
    get_data = rf.BlockchainData
    loading_msg = await bot.send_message(event.chat_id, f"⏳ __Loading Price...__ ⌛")
    info_dict = await get_data("MILKOMEDA", "OccamX").get_ravelin_stats()
    if float(info_dict['peg']) > 1:
        peg_status = "🟢"
    else:
        peg_status = "🔴"
    message_text = f"**RAV:** ${info_dict['rav_price']}\n" \
                   f"- PEG: {peg_status} x{info_dict['peg']}\n" \
                   f"- Circulating: {info_dict['circulating_rav']}\n" \
                   f"--------\n" \
                   f"**RSHARE:** ${info_dict['rshare_price']}\n" \
                   f"- Circulating: {info_dict['circulating_rshare']}\n" \
                   f"- In Boardroom: {info_dict['rshare_locked']} ({info_dict['rshare_locked_pct']}%)\n" \
                   f"--------\n" \
                   f"**ADA**: ${info_dict['ada_price']}" \

    await bot.edit_message(event.chat_id, loading_msg, message_text)


@bot.on(events.NewMessage(pattern="/farms"))
async def show_farms(event):
    get_data = rf.BlockchainData
    loading_msg = await bot.send_message(event.chat_id, f"⏳ __Loading Farms...__ ⌛")
    info_dict = await get_data("MILKOMEDA", "OccamX").get_ravelin_stats()

    rshare_locked_value = '{:0.2f}'.format(float(info_dict['rshare_locked'])*float(info_dict['rshare_price']))
    rshare_locked_value = '{:,}'.format(float(rshare_locked_value))
    rshare_tvl = '{:0.2f}'.format(info_dict['rshare_tvl'])
    rshare_tvl = '{:,}'.format(float(rshare_tvl))
    rav_tvl = '{:0.2f}'.format(info_dict['rav_tvl'])
    rav_tvl = '{:,}'.format(float(rav_tvl))

    message_text = f"👨‍🌾🌽🚜 FARMS 🚜🌽👨‍🌾\n" \
                   f"**RAV-mADA**:\n" \
                   f"- Daily ROI: {info_dict['rav_mada_apr']}%\n" \
                   f"- APR: {float(info_dict['rav_mada_apr'])*365}%\n" \
                   f"- TVL: {rav_tvl}\n" \
                   f"--------\n" \
                   f"**RSHARE-mADA**:\n" \
                   f"- Daily ROI: {info_dict['rshare_mada_apr']}%\n" \
                   f"- APR: {float(info_dict['rshare_mada_apr'])*365}%\n" \
                   f"- TVL: {rshare_tvl}" \

    await bot.edit_message(event.chat_id, loading_msg, message_text)


@bot.on(events.NewMessage(pattern="/boardroom"))
async def show_boardroom(event):
    get_data = rf.BlockchainData
    loading_msg = await bot.send_message(event.chat_id, f"⏳ __Loading Boardroom...__ ⌛")
    info_dict = await get_data("MILKOMEDA", "OccamX").get_ravelin_stats()
    rshare_staked_value = '{:0.2f}'.format(float(info_dict['rshare_locked'])*float(info_dict['rshare_price']))
    rshare_staked_value = '{:,}'.format(float(rshare_staked_value))

    message_text = f"💼👔🍾 BOARDROOM 🍾👔💼\n" \
                   f"- Current Epoch: {info_dict['current_epoch']}\n" \
                   f"- Next Epoch in: {info_dict['next_epoch']}\n" \
                   f"- RSHARE Staked: (${rshare_staked_value}) {info_dict['rshare_locked']} ({info_dict['rshare_locked_pct']}%)\n" \
                   f"- Daily ROI: {info_dict['boardroom_apr']}%\n" \
                   f"- APR: {float(info_dict['boardroom_apr'])*365}%"

    await bot.edit_message(event.chat_id, loading_msg, message_text)


@bot.on(events.NewMessage(pattern="/stats"))
async def show_full_price(event):
    if project_presets['price']['enabled'] == 0:
        return
    get_data = rf.BlockchainData
    loading_msg = await bot.send_message(event.chat_id, f"⏳ __Loading stats...__ ⌛")
    info_dict = await get_data("MILKOMEDA", "OccamX").get_ravelin_stats()
    if float(info_dict['peg']) > 1:
        peg_status = "🟢"
    else:
        peg_status = "🔴"

    rshare_locked_value = '{:0.2f}'.format(float(info_dict['rshare_locked'])*float(info_dict['rshare_price']))
    rshare_locked_value = '{:,}'.format(float(rshare_locked_value))
    rshare_tvl = '{:0.2f}'.format(info_dict['rshare_tvl'])
    rshare_tvl = '{:,}'.format(float(rshare_tvl))
    rav_tvl = '{:0.2f}'.format(info_dict['rav_tvl'])
    rav_tvl = '{:,}'.format(float(rav_tvl))

    message_text = f"🤑💰💸 TOKENS 💸💰🤑\n" \
                f"**RAV**:\n" \
                f"- ${info_dict['rav_price']}\n" \
                f"- PEG: {peg_status} x{info_dict['peg']}\n" \
                f"- Circulating: {info_dict['circulating_rav']}\n" \
                f"--------\n" \
                f"**RSHARE**:\n" \
                f"- ${info_dict['rshare_price']}\n" \
                f"- Circulating: {info_dict['circulating_rshare']}\n" \
                f"--------\n" \
                f"**ADA**:\n" \
                f"- ${info_dict['ada_price']}\n" \
                f"-------------------------------------------\n" \
                f"👨‍🌾🌽🚜 FARMS 🚜🌽👨‍🌾\n" \
                f"**RAV-mADA**:\n" \
                f"- Daily ROI: {info_dict['rav_mada_apr']}%\n" \
                f"- APR: {'{:0.2f}'.format(float(info_dict['rav_mada_apr'])*365)}%\n" \
                f"- TVL: ${rav_tvl}\n" \
                f"--------\n" \
                f"**RSHARE-mADA**:\n" \
                f"- Daily ROI: {info_dict['rshare_mada_apr']}%\n" \
                f"- APR: {'{:0.2f}'.format(float(info_dict['rshare_mada_apr'])*365)}%\n" \
                f"- TVL: ${rshare_tvl}\n" \
                f"-------------------------------------------\n" \
                f"💼👔🍾 BOARDROOM 🍾👔💼\n" \
                f"- Current Epoch: {info_dict['current_epoch']}\n" \
                f"- Next Epoch in: {info_dict['next_epoch']}\n" \
                f"- RSHARE Staked:\n" \
                   f"- - Amount: {info_dict['rshare_locked']}\n" \
                   f"- - Worth: ${rshare_locked_value}\n" \
                   f"- - {info_dict['rshare_locked_pct']}% of circulating.\n" \
                f"- Daily ROI: {info_dict['boardroom_apr']}%\n" \
                f"- APR: {'{:0.2f}'.format(float(info_dict['boardroom_apr'])*365)}%\n" \
                f"-------------------------------------------\n" \
                f"💵 💵 TVL: ${'{:,}'.format(float(info_dict['tvl']))} 💵 💵\n" \
                   f"- __Excluding genesis pools__"

    await bot.edit_message(event.chat_id, loading_msg, message_text)


# Function for enabling/disabling welcome message
@bot.on(events.CallbackQuery(func=toggle_settings_func))
async def toggle_settings(event):
    s_welcome = ("welcome", ["settings", "welcome"])
    s_captcha = ("captcha", ["settings", 'captcha'])
    s_custom_commands = ("custom", ["settings", 'custom_commands'])
    s_banned_words = ("words", ["settings", 'banned_words'])
    s_banned_links = ("links", ["settings", 'banned_links'])
    s_banned_names = ("names", ["settings", 'banned_names'])

    s_list = [s_welcome, s_captcha, s_banned_words, s_banned_links, s_banned_names, s_custom_commands]
    status_list = []

    for s in s_list:
        if s[0] in str(event.data):
            enabled = project_presets[(s[1][0])][(s[1][1])]['enabled']
            if enabled == 1:
                status = (s[0], "🔴 DISABLED")
                status_list.append(status)
                project_presets[(s[1][0])][(s[1][1])]['enabled'] = 0
            else:
                status = (s[0], "🟢 ENABLED")
                status_list.append(status)
                project_presets[(s[1][0])][(s[1][1])]['enabled'] = 1

    for st in status_list:
        for i,v in enumerate(config_buttons):
            if st[0].lower() in v[0].text.lower():
                msg_text = re.findall(r"(.*:)", v[0].text)[0]
                v[0].text = f'{msg_text} {st[1]}'
                config_buttons.pop(i)
                config_buttons.insert(i, [v[0]])

    with open(presets, "w") as w:
        json.dump(project_presets, w)
    await bot.edit_message(event.query.user_id, message=event.query.msg_id, buttons=config_buttons)


# Function for editing banned words
@bot.on(events.CallbackQuery(func=edit_banned_words))
async def edit_banned_words(event):
    if b"add" in event.data:
        user_id = event.query.user_id
        msg_to_edit = await bot.send_message(event.chat_id, "Type the word(s) you want to add, separated by commas.\n"
                                              "Or type 'cancel' to perform different action.\n"
                                              "__Example: word1, word2, word3, word4__")
        async with bot.conversation(event.chat_id) as conv:
            await_reply = conv.wait_event(events.NewMessage(from_users=user_id), timeout=60)
            reply = await await_reply
            reply_message = reply.original_update.message.message
            if "," in reply_message:
                words_to_add = str(reply_message).split(", ")
            elif "cancel" in reply_message:
                await bot.edit_message(msg_to_edit, "Cancelled action.", buttons=Button.inline("Clear message.", data=b'deletethis'))
                await bot.delete_messages(event.chat_id, message_ids=[reply.original_update.message.id])
                return
            else:
                words_to_add = [str(reply_message)]
            with open(filepath_bin+"/banned_words.json", "w") as w:
                for word in words_to_add:
                    banned_words_l.append(word)
                json.dump({"words":banned_words_l}, w)
            await bot.delete_messages(event.chat_id, message_ids=[reply.original_update.message.id])

        await bot.edit_message(msg_to_edit, f"Added {words_to_add} to list.", buttons=Button.inline("Clear message.", data=b'deletethis'))
    elif b'remove' in event.data:
        delete_list = []
        for word in banned_words_l:
            delete_msg = await bot.send_message(event.chat_id, word, buttons=[Button.inline("❌", data=f"delete-{word}")])
            delete_list.append(delete_msg.id)
        cancel_msg = await bot.send_message(event.chat_id, f"🟢 Finished loading.\n"
                                                           f"Do you want to clean up the chat?", buttons=[Button.inline("Yes", "clear-yes"), Button.inline("No", "clear-no")])
        delete_list.append(cancel_msg.id)
        while True:
            async with bot.conversation(event.chat_id) as conv:
                await_reply = conv.wait_event(events.CallbackQuery(), timeout=360)
                reply = await await_reply
                reply_data = reply.data
            if b"yes" in reply_data:
                await bot.delete_messages(event.chat_id, message_ids=delete_list)
                return
            elif b'no' in reply_data:
                await bot.send_message(event.chat_id, f"Okay, carry on!", buttons=Button.inline("Clear message.", data=b'deletethis'))
                break
            else:
                pass
    elif b'delete' in event.data:
        delete_word = re.findall(r"-(.*)'", str(event.data))[0]
        for i in banned_words_l:
            if i == delete_word:
                banned_words_l.pop(banned_words_l.index(i))
                with open(filepath_bin+"/banned_words.json", "w") as w:
                    json.dump({"words":banned_words_l}, w)
                await bot.delete_messages(event.chat_id, [event.query.msg_id])


# Function for editing allowed links
@bot.on(events.CallbackQuery(func=edit_allowed_links))
async def edit_allowed_links(event):
    if b"add" in event.data:
        user_id = event.query.user_id
        msg_to_edit = await bot.send_message(event.chat_id, "Type the link/keyword you want to add, separated by commas.\n"
                                              "__Example: link1, word1, word2, link2__")
        async with bot.conversation(event.chat_id) as conv:
            await_reply = conv.wait_event(events.NewMessage(from_users=user_id), timeout=60)
            reply = await await_reply
            reply_message = reply.original_update.message.message
            if "," in reply_message:
                words_to_add = str(reply_message).split(", ")
            elif "cancel" in reply_message:
                await bot.edit_message(msg_to_edit, "Cancelled action.", buttons=Button.inline("Clear message.", data=b'deletethis'))
                await bot.delete_messages(event.chat_id, message_ids=[reply.original_update.message.id])
                return
            else:
                words_to_add = [str(reply_message)]
            with open(filepath_bin+"/allowed_links.json", "w") as w:
                for word in words_to_add:
                    allowed_links_l.append(word)
                json.dump({"links":allowed_links_l}, w)
            await bot.delete_messages(event.chat_id, message_ids=[reply.original_update.message.id])

        await bot.edit_message(msg_to_edit, f"Added {words_to_add} to list.", buttons=Button.inline("Clear message.", data=b'deletethis'))

    elif b'remove' in event.data:
        delete_list = []
        for word in allowed_links_l:
            delete_msg = await bot.send_message(event.chat_id, word, buttons=[Button.inline("❌", data=f"link-delete-{word}")])
            delete_list.append(delete_msg.id)
        cancel_msg = await bot.send_message(event.chat_id, f"🟢 Finished loading.\n"
                                                           f"Do you want to clean up the chat?", buttons=[Button.inline("Yes", "clear-yes"), Button.inline("No", "clear-no")])
        delete_list.append(cancel_msg.id)
        while True:
            async with bot.conversation(event.chat_id) as conv:
                await_reply = conv.wait_event(events.CallbackQuery(), timeout=360)
                reply = await await_reply
                reply_data = reply.data
            if b"yes" in reply_data:
                await bot.delete_messages(event.chat_id, message_ids=delete_list)
                return
            elif b'no' in reply_data:
                await bot.send_message(event.chat_id, f"Okay, carry on!", buttons=Button.inline("Clear message.", data=b'deletethis'))
                break
            else:
                pass
    elif b'link-delete' in event.data:
        delete_word = re.findall(r"delete-(.*)'", str(event.data))[0]
        for i in allowed_links_l:
            if i == delete_word:
                allowed_links_l.pop(allowed_links_l.index(i))
                with open(filepath_bin+"/allowed_links.json", "w") as w:
                    json.dump({"links":allowed_links_l}, w)
                await bot.delete_messages(event.chat_id, [event.query.msg_id])


# Function for editing allowed links
@bot.on(events.CallbackQuery(func=edit_custom_commands))
async def edit_custom_cmds(event):
    if b"add" in event.data:
        user_id = event.query.user_id
        first_msg = await bot.send_message(event.chat_id, "What kind of command do you want to add?",
                                              buttons=[[Button.inline("1. Send Text", data=b'1')],
                                                       [Button.inline("2. Links as Buttons", data=b'2')],
                                                       [Button.inline("3. Send File(s)", data=b'3')],
                                                       [Button.inline("4. Countdown", data=b'4')],
                                                       [Button.inline("Clear message.", data=b'deletethis')]])
        async with bot.conversation(event.chat_id) as conv:
            await_reply = conv.wait_event(events.CallbackQuery(), timeout=60)
            reply = await await_reply
            reply_data = reply.data
            await bot.delete_messages(event.chat_id, message_ids=first_msg.id)

        if reply_data == b'1':
            msg_to_edit = await bot.send_message(event.chat_id, f"❗ What do you want to name the command?\n----------------------------------------\n"
                                                  f"ℹ__ This is what members will type to use the command.__\n"
                                                  f"__Can be with or without /__")
            async with bot.conversation(event.chat_id) as conv:
                await_reply = conv.wait_event(events.NewMessage(from_users=user_id), timeout=60)
                reply = await await_reply
                command_name = reply.original_update.message.message
                await bot.delete_messages(event.chat_id, message_ids=reply.original_update.message.id)

            await bot.edit_message(event.chat_id, message=msg_to_edit.id, text=f"Name: **{command_name}**\n----------------------------------------\n"
                                                                               f"❗ Do you want this to work with and without the / as well?\n----------------------------------------\n"
                                                  f"ℹ__For example if you have command '/test' it will also work by just typing 'test'__",
                                   buttons=[Button.inline("Yes!", data=b'yes'), Button.inline("No!", data=b'no')])
            async with bot.conversation(event.chat_id) as conv:
                await_reply = conv.wait_event(events.CallbackQuery(), timeout=60)
                reply = await await_reply
                reply_data = reply.data

            if reply_data == b'yes':
                if "/" in command_name:
                    command_name = f'{command_name}, {command_name.strip("/")}'
                else:
                    command_name = f'/{command_name}, {command_name}'

            await bot.edit_message(event.chat_id, message=msg_to_edit.id, text=f"Name: **{command_name}**\n----------------------------------------\n"
                                                  f"❗ Enter text to send when command is used.\n----------------------------------------\n"
                                                  f"ℹ__This is what the bot will send as a message in the chat__")
            async with bot.conversation(event.chat_id) as conv:
                await_reply = conv.wait_event(events.NewMessage(from_users=user_id), timeout=60)
                reply = await await_reply
                command_message = reply.original_update.message.message
                await bot.delete_messages(event.chat_id, message_ids=reply.original_update.message.id)

            await bot.edit_message(event.chat_id, message=msg_to_edit.id, text=f"Name: **{command_name}**\n----------------------------------------\n"
                                                  f"Message: **{command_message}**\n----------------------------------------\n"
                                                  f"❗ Give the command a description.\n----------------------------------------\n"
                                                  f"ℹ__This is what will show as short description when someone use the /help command__")
            async with bot.conversation(event.chat_id) as conv:
                await_reply = conv.wait_event(events.NewMessage(from_users=user_id), timeout=60)
                reply = await await_reply
                command_desc = reply.original_update.message.message
                await bot.delete_messages(event.chat_id, message_ids=reply.original_update.message.id)

            await bot.edit_message(event.chat_id, message=msg_to_edit.id, text=f"✅ New Command Created!\n"
                                                  f"Name: {command_name}\n"
                                                  f"Message: {command_message}\n"
                                                  f"Description: {command_desc}", buttons=Button.inline("Clear message.", data=b'deletethis'))
            with open(filepath_bin+"/custom_commands.json", "w") as w:
                custom_commands_dict[f'{command_name}'] = {
                    "message": str(command_message),
                    "description": str(command_desc),
                    "buttons": {},
                    "files": []
                }
                json.dump(custom_commands_dict, w)

        elif reply_data == b'2':
            msg_to_edit = await bot.send_message(event.chat_id, f"❗ What do you want to name the command?\n----------------------------------------\n"
                                                  f"ℹ__ This is what members will type to use the command.__\n"
                                                  f"__Can be with or without /__")
            async with bot.conversation(event.chat_id) as conv:
                await_reply = conv.wait_event(events.NewMessage(from_users=user_id), timeout=60)
                reply = await await_reply
                command_name = reply.original_update.message.message
                await bot.delete_messages(event.chat_id, message_ids=reply.original_update.message.id)

            await bot.edit_message(event.chat_id, message=msg_to_edit.id, text=f"Name: **{command_name}**\n----------------------------------------\n"
                                                                               f"❗ Do you want this to work with and without the / as well?\n----------------------------------------\n"
                                                  f"ℹ__For example if you have command '/test' it will also work by just typing 'test'__",
                                   buttons=[Button.inline("Yes!", data=b'yes'), Button.inline("No!", data=b'no')])
            async with bot.conversation(event.chat_id) as conv:
                await_reply = conv.wait_event(events.CallbackQuery(), timeout=60)
                reply = await await_reply
                reply_data = reply.data

            if reply_data == b'yes':
                if "/" in command_name:
                    command_name = f'{command_name}, {command_name.strip("/")}'
                else:
                    command_name = f'/{command_name}, {command_name}'

            await bot.edit_message(event.chat_id, message=msg_to_edit.id, text=f"Name: **{command_name}**\n----------------------------------------\n"
                                                  f"❗ Enter caption to send with the buttons.\n----------------------------------------\n"
                                                  f"ℹ__This is what will show as text above the buttons__")
            async with bot.conversation(event.chat_id) as conv:
                await_reply = conv.wait_event(events.NewMessage(from_users=user_id), timeout=60)
                reply = await await_reply
                command_message = reply.original_update.message.message
                await bot.delete_messages(event.chat_id, message_ids=reply.original_update.message.id)

            await bot.edit_message(event.chat_id, message=msg_to_edit.id, text=f"Name: **{command_name}**\n----------------------------------------\n"
                                                  f"Caption: **{command_message}**\n----------------------------------------\n"
                                                  f"❗ Give the command a description.\n----------------------------------------\n"
                                                  f"ℹ__This is what will show as short description when someone use the /help command__")
            async with bot.conversation(event.chat_id) as conv:
                await_reply = conv.wait_event(events.NewMessage(from_users=user_id), timeout=60)
                reply = await await_reply
                command_desc = reply.original_update.message.message
                await bot.delete_messages(event.chat_id, message_ids=reply.original_update.message.id)

            await bot.edit_message(event.chat_id, message=msg_to_edit.id, text=f"Name: **{command_name}**\n----------------------------------------\n"
                                                  f"Caption: **{command_message}**\n----------------------------------------\n"
                                                  f"Description: **{command_desc}**\n----------------------------------------\n"
                                                  f"❗ Enter the button text and link URL separated by comma.\n----------------------------------------\n"
                                                  f"ℹ__For example: Website, https://gamma.polypulsar.farm/__")
            buttons = {}
            count = 1
            async with bot.conversation(event.chat_id) as conv:
                await_reply = conv.wait_event(events.NewMessage(from_users=user_id), timeout=60)
                reply = await await_reply
                command_button = reply.original_update.message.message
                command_button = str(command_button).split(", ")
                buttons[str(count)] = command_button
                await bot.delete_messages(event.chat_id, message_ids=reply.original_update.message.id)

            await bot.edit_message(event.chat_id, message=msg_to_edit.id, text=f"Name: **{command_name}**\n----------------------------------------\n"
                                                                 f"Caption: **{command_message}**\n----------------------------------------\n"
                                                                 f"Description: **{command_desc}**\n----------------------------------------\n"
                                                                 f"Buttons: **{buttons}**\n----------------------------------------\n"
                                                                 f"❗ To add more buttons, enter the button text and link URL separated by comma.\n----------------------------------------\n"
                                                                 f"❗ Type 'done' when you're done adding buttons!")
            while True:
                async with bot.conversation(event.chat_id) as conv:
                    await_reply = conv.wait_event(events.NewMessage(from_users=user_id), timeout=60)
                    reply = await await_reply
                    command_reply = reply.original_update.message.message
                    await bot.delete_messages(event.chat_id, message_ids=reply.original_update.message.id)

                if "done" in command_reply:
                    break
                else:
                    command_button = str(command_reply).split(", ")
                    count += 1
                    buttons[str(count)] = command_button
                    await bot.edit_message(event.chat_id, message=msg_to_edit.id, text=f"Name: **{command_name}**\n----------------------------------------\n"
                                                                                        f"Caption: **{command_message}**\n----------------------------------------\n"
                                                                                        f"Description: **{command_desc}**\n----------------------------------------\n"
                                                                                        f"Buttons: **{buttons}**\n----------------------------------------\n"
                                                                                        f"❗ To add more buttons, enter the button text and link URL separated by comma.\n----------------------------------------\n"
                                                                                        f"❗ Type 'done' when you're done adding buttons!")
            await bot.edit_message(event.chat_id, message=msg_to_edit.id, text=f"✅ New Command Created!\n"
                                                                               f"Name: {command_name}\n"
                                                                               f"Caption: {command_message}\n"
                                                                               f"Description: {command_desc}\n"
                                                                               f"Buttons: {buttons}", buttons=Button.inline("Clear message.", data=b'deletethis'))
            with open(filepath_bin+"/custom_commands.json", "w") as w:
                custom_commands_dict[f'{command_name}'] = {
                    "message": str(command_message),
                    "description": str(command_desc),
                    "buttons": buttons,
                    "files": []
                }
                json.dump(custom_commands_dict, w)

        elif reply_data == b'3':
            msg_to_edit = await bot.send_message(event.chat_id, f"❗ What do you want to name the command?\n----------------------------------------\n"
                                                                f"ℹ__ This is what members will type to use the command.__\n"
                                                                f"__Can be with or without /__")
            async with bot.conversation(event.chat_id) as conv:
                await_reply = conv.wait_event(events.NewMessage(from_users=user_id), timeout=60)
                reply = await await_reply
                command_name = reply.original_update.message.message
                await bot.delete_messages(event.chat_id, message_ids=reply.original_update.message.id)

            await bot.edit_message(event.chat_id, message=msg_to_edit.id, text=f"Name: **{command_name}**\n----------------------------------------\n"
                                                                               f"❗ Do you want this to work with and without the / as well?\n----------------------------------------\n"
                                                                               f"ℹ__For example if you have command '/test' it will also work by just typing 'test'__",
                                   buttons=[Button.inline("Yes!", data=b'yes'), Button.inline("No!", data=b'no')])
            async with bot.conversation(event.chat_id) as conv:
                await_reply = conv.wait_event(events.CallbackQuery(), timeout=60)
                reply = await await_reply
                reply_data = reply.data

            if reply_data == b'yes':
                if "/" in command_name:
                    command_name = f'{command_name}, {command_name.strip("/")}'
                else:
                    command_name = f'/{command_name}, {command_name}'

            await bot.edit_message(event.chat_id, message=msg_to_edit.id, text=f"Name: **{command_name}**\n----------------------------------------\n"
                                                                               f"❗ Enter caption to send with the file(s).\n----------------------------------------\n"
                                                                               f"ℹ__This is what will show as text__")
            async with bot.conversation(event.chat_id) as conv:
                await_reply = conv.wait_event(events.NewMessage(from_users=user_id), timeout=60)
                reply = await await_reply
                command_message = reply.original_update.message.message
                await bot.delete_messages(event.chat_id, message_ids=reply.original_update.message.id)

            await bot.edit_message(event.chat_id, message=msg_to_edit.id, text=f"Name: **{command_name}**\n----------------------------------------\n"
                                                                               f"Caption: **{command_message}**\n----------------------------------------\n"
                                                                               f"❗ Give the command a description.\n----------------------------------------\n"
                                                                               f"ℹ__This is what will show as short description when someone use the /help command__")
            async with bot.conversation(event.chat_id) as conv:
                await_reply = conv.wait_event(events.NewMessage(from_users=user_id), timeout=60)
                reply = await await_reply
                command_desc = reply.original_update.message.message
                await bot.delete_messages(event.chat_id, message_ids=reply.original_update.message.id)

            await bot.edit_message(event.chat_id, message=msg_to_edit.id, text=f"Name: **{command_name}**\n----------------------------------------\n"
                                                                               f"Caption: **{command_message}**\n----------------------------------------\n"
                                                                               f"Description: **{command_desc}**\n----------------------------------------\n"
                                                                               f"❗ Send the file that you want to add to the command.\n----------------------------------------\n"
                                                                               f"ℹ__Can be photo, pdf, gif or sticker__")
            files = []
            count = 1
            async with bot.conversation(event.chat_id) as conv:
                await_reply = conv.wait_event(events.NewMessage(from_users=user_id), timeout=60)
                reply = await await_reply
                command_file = reply.original_update.message.media
                await bot.delete_messages(event.chat_id, message_ids=reply.original_update.message.id)

                if isinstance(command_file, MessageMediaPhoto):
                    file_name = f'photo_{count}'
                    file_data = pickle.dumps(command_file)
                elif isinstance(command_file, MessageMediaDocument):
                    if "pdf" in str(command_file.document.mime_type):
                        file_name = f"pdf_{count}"
                        file_data = pickle.dumps(command_file)
                    elif "sticker" in str(command_file.document.mime_type):
                        file_name = f'sticker_{count}'
                        file_data = pickle.dumps(command_file)
                    elif "video" in str(command_file.document.mime_type):
                        file_name = f'video_{count}'
                        file_data = pickle.dumps(command_file)
                query = db.insert(files_table).values(command=str(command_name), file_name=file_name, file_data=file_data)
                connection.execute(query)
                files.append(file_name)
            await bot.edit_message(event.chat_id, message=msg_to_edit.id, text=f"Name: **{command_name}**\n----------------------------------------\n"
                                                                               f"Caption: **{command_message}**\n----------------------------------------\n"
                                                                               f"Description: **{command_desc}**\n----------------------------------------\n"
                                                                               f"File(s): **{files}**\n----------------------------------------\n"
                                                                               f"❗ Send files to add more to this command.\n----------------------------------------\n"
                                                                               f"❗ Type 'done' when you're done adding files!")
            while True:
                async with bot.conversation(event.chat_id) as conv:
                    await_reply = conv.wait_event(events.NewMessage(from_users=user_id), timeout=60)
                    reply = await await_reply
                    command_reply = reply.original_update.message.message
                    await bot.delete_messages(event.chat_id, message_ids=reply.original_update.message.id)

                if "done" in command_reply:
                    break
                else:
                    count += 1
                    command_file = reply.original_update.message.media
                    await bot.delete_messages(event.chat_id, message_ids=reply.original_update.message.id)
                    if isinstance(command_file, MessageMediaPhoto):
                        file_name = f'photo_{count}'
                        file_data = pickle.dumps(command_file)
                    elif isinstance(command_file, MessageMediaDocument):
                        if "pdf" in str(command_file.document.mime_type):
                            file_name = f"pdf_{count}"
                            file_data = pickle.dumps(command_file)
                        elif "sticker" in str(command_file.document.mime_type):
                            file_name = f'sticker_{count}'
                            file_data = pickle.dumps(command_file)
                        elif "video" in str(command_file.document.mime_type):
                            file_name = f'video_{count}'
                            file_data = pickle.dumps(command_file)
                    query = db.insert(files_table).values(command=str(command_name), file_name=file_name, file_data=file_data)
                    connection.execute(query)
                    files.append(file_name)
                    await bot.edit_message(event.chat_id, message=msg_to_edit.id, text=f"Name: **{command_name}**\n----------------------------------------\n"
                                                                                       f"Caption: **{command_message}**\n----------------------------------------\n"
                                                                                       f"Description: **{command_desc}**\n----------------------------------------\n"
                                                                                       f"File(s): **{files}**\n----------------------------------------\n"
                                                                                       f"❗ Send files to add more to this command.\n----------------------------------------\n"
                                                                                       f"❗ Type 'done' when you're done adding files!")
            await bot.edit_message(event.chat_id, message=msg_to_edit.id, text=f"✅ New Command Created!\n"
                                                                               f"Name: {command_name}\n"
                                                                               f"Caption: {command_message}\n"
                                                                               f"Description: {command_desc}\n"
                                                                               f"File(s): {files}", buttons=Button.inline("Clear message.", data=b'deletethis'))

            with open(filepath_bin+"/custom_commands.json", "w") as w:
                custom_commands_dict[f'{command_name}'] = {
                    "message": str(command_message),
                    "description": str(command_desc),
                    "buttons": {},
                    "files": files
                }
                json.dump(custom_commands_dict, w)

    elif b'remove' in event.data:
        delete_list = []
        for word in custom_commands_names:
            delete_msg = await bot.send_message(event.chat_id, word, buttons=[Button.inline("❌", data=f"custom-delete-{word}")])
            delete_list.append(delete_msg.id)
        cancel_msg = await bot.send_message(event.chat_id, f"🟢 Finished loading.\n"
                                                           f"Do you want to clean up the chat?", buttons=[Button.inline("Yes", "clear-yes"), Button.inline("No", "clear-no")])
        delete_list.append(cancel_msg.id)
        while True:
            async with bot.conversation(event.chat_id) as conv:
                await_reply = conv.wait_event(events.CallbackQuery(), timeout=360)
                reply = await await_reply
                reply_data = reply.data
            if b"yes" in reply_data:
                await bot.delete_messages(event.chat_id, message_ids=delete_list)
                return
            elif b'no' in reply_data:
                await bot.send_message(event.chat_id, f"Okay, carry on!", buttons=Button.inline("Clear message.", data=b'deletethis'))
                break
            else:
                pass

    elif b'custom-delete' in event.data:
        new_dict = custom_commands_dict
        delete_word = re.findall(r"delete-(.*)'", str(event.data))[0]
        if delete_word in custom_commands_names:
            del new_dict[delete_word]
            with open(filepath_bin+"/custom_commands.json", "w") as w:
                json.dump(new_dict, w)
            await bot.delete_messages(event.chat_id, [event.query.msg_id])
            try:
                query = files_table.delete().where(files_table.c.command == delete_word)
                engine.execute(query)
            except:
                pass


# Function for editing admins
@bot.on(events.CallbackQuery(func=edit_admins))
async def edit_admins(event):
    if b"add" in event.data:
        user_id = event.query.user_id
        msg_to_edit = await bot.send_message(event.chat_id, "Type the usernames you want to add, with @ and separated by commas.\n"
                                              "Or type 'cancel' to perform different action.\n"
                                              "__Example: @admin1, @admin2, @admin3, @admin3__")
        async with bot.conversation(event.chat_id) as conv:
            await_reply = conv.wait_event(events.NewMessage(from_users=user_id), timeout=60)
            reply = await await_reply
            reply_message = reply.original_update.message.message
            if "," in reply_message:
                words_to_add = str(reply_message).split(", ")
            elif "cancel" in reply_message:
                await bot.edit_message(msg_to_edit, "Cancelled action.", buttons=Button.inline("Clear message.", data=b'deletethis'))
                await bot.delete_messages(event.chat_id, message_ids=[reply.original_update.message.id])
                return
            else:
                words_to_add = [str(reply_message)]
            with open(filepath_bin+"/admin_list.json", "w") as w:
                added_list = []
                for word in words_to_add:
                    try:
                        user = await bot.get_entity(word)
                        admin_list.append(user.id)
                        added_list.append(word)
                    except:
                        await bot.edit_message(msg_to_edit, f"{word} not added! Invalid username.", buttons=Button.inline("Clear message.", data=b'deletethis'))
                json.dump({"admins":admin_list}, w)
            await bot.delete_messages(event.chat_id, message_ids=[reply.original_update.message.id])
        if not added_list:
            return
        await bot.edit_message(msg_to_edit, f"Added {added_list} to list.", buttons=Button.inline("Clear message.", data=b'deletethis'))

    elif b'remove' in event.data:
        delete_list = []
        for word in admin_list:
            user = await bot.get_entity(int(word))
            delete_msg = await bot.send_message(event.chat_id, str(user.username), buttons=[Button.inline("❌", data=f"admin-delete-{str(word)}")])
            delete_list.append(delete_msg.id)
        cancel_msg = await bot.send_message(event.chat_id, f"🟢 Finished loading.\n"
                                                           f"Do you want to clean up the chat?", buttons=[Button.inline("Yes", "clear-yes"), Button.inline("No", "clear-no")])
        delete_list.append(cancel_msg.id)
        while True:
            async with bot.conversation(event.chat_id) as conv:
                await_reply = conv.wait_event(events.CallbackQuery(), timeout=360)
                reply = await await_reply
                reply_data = reply.data
            if b"yes" in reply_data:
                await bot.delete_messages(event.chat_id, message_ids=delete_list)
                return
            elif b'no' in reply_data:
                await bot.send_message(event.chat_id, f"Okay, carry on!", buttons=Button.inline("Clear message.", data=b'deletethis'))
                break
            else:
                pass
    elif b'admin-delete' in event.data:
        delete_word = re.findall(r"delete-(.*)'", str(event.data))[0]
        user = await bot.get_entity(int(delete_word))
        for i in admin_list:
            if i == user.id:
                admin_list.pop(admin_list.index(i))
                with open(filepath_bin+"/admin_list.json", "w") as w:
                    json.dump({"admins":admin_list}, w)
                await bot.delete_messages(event.chat_id, [event.query.msg_id])


# Function for catching button clicks
@bot.on(events.CallbackQuery)
async def handler(event):
    peer_user = event.original_update.user_id
    # Button presses returns byte values that can be used to determine which action should be performed
    ### ADMIN BUTTONS ###

    # Check banned users
    if event.data == b'check-banned':
        try:
            user_id = event.query.user_id
            kicked = await bot.get_participants(channel_id, filter=ChannelParticipantsKicked)
            kicked_len = len(kicked)
            id_list = []
            if str(kicked)[1] == ",":
                await bot.send_message(event.chat_id, "No banned users", buttons=Button.inline("Clear message.", data=b'deletethis'))
            elif kicked_len > 10:
                for i in reversed(range((kicked_len-9), kicked_len)):
                    user = kicked[i]
                    unban_msg = await bot.send_message(event.chat_id, f"{user.first_name} {user.last_name}\n@{user.username}",
                                                       buttons=[Button.inline('Unban', "unban-"+str(user.id))])
                    id_list.append(unban_msg.id)
                too_long = await bot.send_message(event.chat_id, f"List too long to fully load!\n"
                                                                 f"Loaded 10 most recently banned users.\n"
                                                                 f"Total number of banned users: {kicked_len}\n",
                                                  buttons=[[Button.inline('🔽 Load 10 more', "load-10-"+str(kicked_len-10)), Button.inline('⏬ Load 20 more', "load-20-"+str(kicked_len-10))],
                                                           [Button.inline('🔴 Cancel', 'cancel'), Button.inline('🔍 Search', "search")]])
                id_list.append(too_long.id)
                while True:
                    async with bot.conversation(event.chat_id) as conv:
                        await_reply = conv.wait_event(events.CallbackQuery(), timeout=60)
                        reply = await await_reply
                        reply_data = reply.data
                    if b"load" in reply_data:
                        reply_query = re.findall(r".*([0-9].)-([0-9].*)'", str(reply_data))[0]
                        kicked_len = int(reply_query[1])
                        load_amount = reply_query[0]
                        print(kicked_len)
                        for i in reversed(range((kicked_len-int(load_amount)-1), kicked_len)):
                            user = kicked[i]
                            unban_msg = await bot.send_message(event.chat_id, f"{user.first_name} {user.last_name}\n@{user.username}",
                                                               buttons=[Button.inline('Unban', "unban-"+str(user.id))])
                            id_list.append(unban_msg.id)
                        load_more = await bot.send_message(event.chat_id, f"Loaded {load_amount} more banned users.\n",
                                                           buttons=[[Button.inline('🔽 Load 10 more', "load-10-"+str(kicked_len-10)), Button.inline('⏬ Load 20 more', "load-20-"+str(kicked_len-int(load_amount)))],
                                                                    [Button.inline('🔴 Cancel', 'cancel'), Button.inline('🔍 Search', "search")]])
                        id_list.append(load_more.id)
                    elif b"search" in reply_data:
                        search_msg = await bot.send_message(event.chat_id, f"Acceptable search terms:\n"
                                                                           f"- Username\n"
                                                                           f"- First name\n"
                                                                           f"- Last name\n"
                                                                           f"- A combination of the above\n"
                                                                           f"__Awaiting input...__")
                        async with bot.conversation(event.chat_id) as conv:
                            await_reply = conv.wait_event(events.NewMessage(from_users=user_id), timeout=60)
                            reply = await await_reply
                            reply_msg = reply.original_update.message.message
                            id_list.append(reply.id)
                        for search_user in kicked:
                            search_term = f"Username: @{search_user.username} \n First name: {search_user.first_name} \n Last name: {search_user.last_name}"
                            if reply_msg.lower() in search_term.lower():
                                search_result = await bot.send_message(event.chat_id, f"**Found:**\n{search_term}",
                                                                       buttons=[Button.inline('Unban', "unban-"+str(search_user.id))])
                                id_list.append(search_result.id)
                        await bot.delete_messages(event.chat_id, message_ids=[search_msg.id])
                        search_complete = await bot.send_message(event.chat_id, f"Search complete!\n",
                                                                 buttons=[[Button.inline('🔴 Cancel', 'cancel'), Button.inline('🔍 New Search', "new-search")]])
                        id_list.append(search_complete.id)
                    elif b"cancel" in reply_data:
                        break
                cancel_msg = await bot.send_message(event.chat_id, f"Cancelled loading banned users!\n"
                                                                   f"Do you want to clean up the chat?", buttons=[Button.inline("Yes", "clear-yes"), Button.inline("No", "clear-no")])
                id_list.append(cancel_msg.id)
                async with bot.conversation(event.chat_id) as conv:
                    await_reply = conv.wait_event(events.CallbackQuery(), timeout=60)
                    reply = await await_reply
                    reply_data = reply.data
                if b"yes" in reply_data:
                    await bot.delete_messages(event.chat_id, message_ids=id_list)
                    return
                elif b'no' in reply_data:
                    await bot.send_message(event.chat_id, f"Okay, carry on!", buttons=Button.inline("Clear message.", data=b'deletethis'))

            else:
                async for user in bot.iter_participants(channel_id, filter=ChannelParticipantsKicked):
                    try:
                        id_list = []
                        unban_msg = await bot.send_message(event.chat_id, f"{user.first_name} {user.last_name}\n@{user.username}",
                                               buttons=[Button.inline('Unban', "unban-"+str(user.id))])
                        cancel_msg = await bot.send_message(event.chat_id, f"Finished loading.\n"
                                                                           f"Do you want to clean up the chat?", buttons=[Button.inline("Yes", "clear-yes"), Button.inline("No", "clear-no")])
                        id_list.append(cancel_msg.id)
                        id_list.append(unban_msg.id)
                        async with bot.conversation(event.chat_id) as conv:
                            await_reply = conv.wait_event(events.CallbackQuery(), timeout=60)
                            reply = await await_reply
                            reply_data = reply.data
                        if b"yes" in reply_data:
                            await bot.delete_messages(event.chat_id, message_ids=id_list)
                            return
                        elif b'no' in reply_data:
                            await bot.send_message(event.chat_id, f"Okay, carry on!", buttons=Button.inline("Clear message.", data=b'deletethis'))
                    except AttributeError:
                        await bot.send_message(event.chat_id, "No banned users", buttons=Button.inline("Clear message.", data=b'deletethis'))
        except AttributeError:
            await bot.send_message(event.chat_id, "No banned users", buttons=Button.inline("Clear message.", data=b'deletethis'))

    if event.data == b'check-muted':
        try:
            kicked = await bot.get_participants(channel_id, filter=ChannelParticipantsBanned)
            kicked_len = len(kicked)
            id_list = []
            if str(kicked)[1] == ",":
                await bot.send_message(event.chat_id, "No muted users", buttons=Button.inline("Clear message.", data=b'deletethis'))
            elif kicked_len > 10:
                for i in reversed(range((kicked_len-9), kicked_len)):
                    user = kicked[i]
                    unban_msg = await bot.send_message(event.chat_id, f"{user.first_name} {user.last_name}\n@{user.username}",
                                                       buttons=[Button.inline('Unmute', "unmute-"+str(user.id))])
                    id_list.append(unban_msg.id)
                too_long = await bot.send_message(event.chat_id, f"List too long to fully load!\n"
                                                                 f"Loaded 10 most recently muted users.\n"
                                                                 f"Total number of muted users: {kicked_len}\n",
                                                  buttons=[[Button.inline('🔽 Load 10 more', "load-10-"+str(kicked_len-10)), Button.inline('⏬ Load 20 more', "load-20-"+str(kicked_len-10))],
                                                           [Button.inline('🔴 Cancel', 'cancel'), Button.inline('🔍 Search', "search")]])
                id_list.append(too_long.id)
                while True:
                    async with bot.conversation(event.chat_id) as conv:
                        await_reply = conv.wait_event(events.CallbackQuery(), timeout=60)
                        reply = await await_reply
                        reply_data = reply.data
                    if b"load" in reply_data:
                        reply_query = re.findall(r".*([0-9].)-([0-9].*)'", str(reply_data))[0]
                        kicked_len = int(reply_query[1])
                        load_amount = reply_query[0]
                        print(kicked_len)
                        for i in reversed(range((kicked_len-int(load_amount)-1), kicked_len)):
                            user = kicked[i]
                            unban_msg = await bot.send_message(event.chat_id, f"{user.first_name} {user.last_name}\n@{user.username}",
                                                               buttons=[Button.inline('Unmute', "unmute-"+str(user.id))])
                            id_list.append(unban_msg.id)
                        load_more = await bot.send_message(event.chat_id, f"Loaded {load_amount} more muted users.\n",
                                                           buttons=[[Button.inline('🔽 Load 10 more', "load-10-"+str(kicked_len-10)), Button.inline('⏬ Load 20 more', "load-20-"+str(kicked_len-int(load_amount)))],
                                                                    [Button.inline('🔴 Cancel', 'cancel'), Button.inline('🔍 Search', "search")]])
                        id_list.append(load_more.id)
                    elif b"search" in reply_data:
                        if b"new" in reply_data:
                            print(reply)
                        search_msg = await bot.send_message(event.chat_id, f"Acceptable search terms:\n"
                                                                           f"- Username\n"
                                                                           f"- First name\n"
                                                                           f"- Last name\n"
                                                                           f"- A combination of the above\n"
                                                                           f"__Awaiting input...__")
                        async with bot.conversation(event.chat_id) as conv:
                            await_reply = conv.wait_event(events.NewMessage(from_users=user_id), timeout=60)
                            reply = await await_reply
                            reply_msg = reply.original_update.message.message
                            id_list.append(reply.id)
                        for search_user in kicked:
                            search_term = f"Username: @{search_user.username} \n First name: {search_user.first_name} \n Last name: {search_user.last_name}"
                            if reply_msg.lower() in search_term.lower():
                                search_result = await bot.send_message(event.chat_id, f"**Found:**\n{search_term}",
                                                                       buttons=[Button.inline('Unmute', "unmute-"+str(user.id))])
                                id_list.append(search_result.id)
                        await bot.delete_messages(event.chat_id, message_ids=[search_msg.id])
                        search_complete = await bot.send_message(event.chat_id, f"Search complete!\n",
                                                                 buttons=[[Button.inline('🔴 Cancel', 'cancel'), Button.inline('🔍 New Search', "new-search")]])
                        id_list.append(search_complete.id)
                    elif b"cancel" in reply_data:
                        break
                cancel_msg = await bot.send_message(event.chat_id, f"Cancelled loading muted users!\n"
                                                                   f"Do you want to clean up the chat?", buttons=[Button.inline("Yes", "clear-yes"), Button.inline("No", "clear-no")])
                id_list.append(cancel_msg.id)
                async with bot.conversation(event.chat_id) as conv:
                    await_reply = conv.wait_event(events.CallbackQuery(), timeout=60)
                    reply = await await_reply
                    reply_data = reply.data
                if b"yes" in reply_data:
                    await bot.delete_messages(event.chat_id, message_ids=id_list)
                    return
                elif b'no' in reply_data:
                    await bot.send_message(event.chat_id, f"Okay, carry on!", buttons=Button.inline("Clear message.", data=b'deletethis'))

            else:
                async for user in bot.iter_participants(channel_id, filter=ChannelParticipantsBanned):
                    try:
                        id_list = []
                        unban_msg = await bot.send_message(event.chat_id, f"{user.first_name} {user.last_name}\n@{user.username}",
                                                           buttons=[Button.inline('Unmute', "unmute-"+str(user.id))])
                        cancel_msg = await bot.send_message(event.chat_id, f"Finished loading.\n"
                                                                           f"Do you want to clean up the chat?", buttons=[Button.inline("Yes", "clear-yes"), Button.inline("No", "clear-no")])
                        id_list.append(cancel_msg.id)
                        id_list.append(unban_msg.id)
                        async with bot.conversation(event.chat_id) as conv:
                            await_reply = conv.wait_event(events.CallbackQuery(), timeout=60)
                            reply = await await_reply
                            reply_data = reply.data
                        if b"yes" in reply_data:
                            await bot.delete_messages(event.chat_id, message_ids=id_list)
                            return
                        elif b'no' in reply_data:
                            await bot.send_message(event.chat_id, f"Okay, carry on!", buttons=Button.inline("Clear message.", data=b'deletethis'))
                    except AttributeError:
                        await bot.send_message(event.chat_id, "No muted users", buttons=Button.inline("Clear message.", data=b'deletethis'))
        except AttributeError:
            await bot.send_message(event.chat_id, "No muted users", buttons=Button.inline("Clear message.", data=b'deletethis'))

    # Unmute user
    elif b"unmute" in event.data:
        unbanned = ChatBannedRights(
            until_date= None,
        )
        unban_pattern = re.search(r"unmute-(\d.*)'", str(event.data), flags=re.IGNORECASE)
        user = await bot.get_entity(int(unban_pattern[1]))
        if not user.username and not user.last_name:
            user_id = user.first_name
        elif not user.username:
            user_id = user.first_name, user.last_name
        else:
            user_id = "@"+str(user.username)
        await bot(EditBannedRequest(channel_id, int(unban_pattern[1]), unbanned))
        await bot.send_message(event.chat_id, f"Unmuted {user_id}", buttons=Button.inline("Clear message.", data=b'deletethis'))

    # Unban user
    elif b"unban" in event.data:
        unbanned = ChatBannedRights(
            until_date= None,
        )
        unban_pattern = re.search(r"unban-(\d.*)'", str(event.data), flags=re.IGNORECASE)
        user = await bot.get_entity(int(unban_pattern[1]))
        if not user.username and not user.last_name:
            user_id = user.first_name
        elif not user.username:
            user_id = user.first_name, user.last_name
        else:
            user_id = "@"+str(user.username)
        await bot(EditBannedRequest(channel_id, int(unban_pattern[1]), unbanned))
        await bot.send_message(event.chat_id, f"Unbanned {user_id}", buttons=Button.inline("Clear message.", data=b'deletethis'))

    # New captcha image
    elif b'new-captcha' in event.data:
        tasks = asyncio.all_tasks()
        for i in tasks:
            if i.get_name() == f"new-captcha-{event.chat_id}":
                i.cancel()

    elif b'deletethis' in event.data:
        await bot.delete_messages(event.chat_id, message_ids=[event.original_update.msg_id])


# Function for handling new users joining
@bot.on(events.ChatAction())
async def new_user_join(event):
    await bot.delete_messages(event.chat_id, message_ids=event.action_message.id)

    welcome_message = settings['welcome']['enabled']
    captcha_status = settings['captcha']['enabled']
    banned_names_status = settings['banned_names']['enabled']

    peer_user = event.action_message.from_id.user_id
    first_name = event.user.first_name
    last_name = event.user.last_name
    addressPattern = re.compile(r'0x[\da-f]{40}', flags=re.IGNORECASE)

    banned = ChatBannedRights(
        until_date= int(time())+60,
        view_messages=True,
    )
    unbanned = ChatBannedRights(
        until_date= None,
    )
    perm_banned = ChatBannedRights(
        until_date= None,
        view_messages=True,
    )
    restricted = ChatBannedRights(
        until_date= None,
        send_messages=True,
        send_media=True,
        send_stickers=True,
        send_gifs=True,
        send_games=True,
        send_inline=True,
        embed_links=True
    )
    search_query = db.select([users_table]).where(users_table.columns.peer_id == peer_user)
    ResultProxy = connection.execute(search_query)
    ResultSet = ResultProxy.fetchall()
    if not ResultSet:
        query = db.insert(users_table).values(peer_id=peer_user)
        connection.execute(query)
    if captcha_status == 1:
        if event.user_added or event.user_joined:
            await bot(EditBannedRequest(event.chat_id, event.user_id, restricted))
    else:
        query = db.update(users_table).values(verified=True)
        query = query.where(users_table.columns.peer_id == peer_user)
        connection.execute(query)

    if not event.user.username and not event.user.last_name:
        user_id = event.user.first_name
    elif not event.user.username:
        user_id = event.user.first_name, event.user.last_name
    else:
        user_id = "@"+str(event.user.username)

    inspect_name = None
    if banned_names_status == 1:
        max_warnings = settings['warnings']
        try:
            inspect_name = re.search(addressPattern, (first_name+last_name).lower())
            if inspect_name and event.user_joined or event.user_added:
                warn_count = int(ResultSet[0][1])+1
                query = db.update(users_table).values(warnings=warn_count)
                query = query.where(users_table.columns.peer_id == peer_user)
                connection.execute(query)
                if warn_count == max_warnings-1:
                    warning = await bot.send_message(event.chat_id, f"You're very stubborn {user_id}! Just change your name before you come back!\nYou will be banned for 1 more minute.\n"
                                                                    f"**THIS IS YOUR LAST WARNING BEFORE PERMANENT BAN!**")
                    await asyncio.sleep(10)
                    ban = await bot(EditBannedRequest(event.chat_id, event.user_id, banned))
                    await bot.delete_messages(event.chat_id, message_ids=[int(ban.updates[0].id), warning.id])
                    return
                elif warn_count >= max_warnings:
                    perm_ban_msg = await bot.send_message(event.chat_id, f"{user_id} I told you to change your name.\n"
                                                          f"**P-P-P-PEEEERMA BAAAANNEED!! 🔨🔨🔨**")
                    await asyncio.sleep(10)
                    perm_ban = await bot(EditBannedRequest(event.chat_id, event.user_id, perm_banned))
                    await bot.delete_messages(event.chat_id, message_ids=[int(perm_ban.updates[0].id), perm_ban_msg.id])
                    return
                else:
                    warning = await bot.send_message(event.chat_id, f"{user_id} your name is offensive or is a contract address! Change it before you come back!\nYou will be banned for 1 minute.\n"
                                                                f"**Warning {warn_count}**. You only get **{max_warnings}!**")
                    await asyncio.sleep(10)
                    ban = await bot(EditBannedRequest(event.chat_id, event.user_id, banned))
                    await bot.delete_messages(event.chat_id, message_ids=[int(ban.updates[0].id), warning.id])
                    return
        except TypeError or AttributeError:
            inspect_name = None

    if event.user_joined or event.user_added and not inspect_name:
        if welcome_message == 1:
            message_text = project_presets['welcome_msg']['message']
            message_text = message_text.replace("<user_id>", str(user_id))
            message_text = message_text.replace("<project_name>", str(project_name))
            message_text = message_text.replace("<del_sec>", str(project_presets['welcome_msg']['auto-delete']['timer']))
            message_buttons = []
            buttons = project_presets['welcome_msg']['buttons']
            for button in buttons:
                if buttons[button]:
                    if buttons[button][1]:
                        message_buttons.append([Button.url(text=buttons[button][0], url=buttons[button][1])])
            welcome_msg = await event.respond(message_text, buttons=message_buttons)
            if project_presets['welcome_msg']['auto-delete']['enabled'] == 1:
                asyncio.get_running_loop().create_task(message_timer(message_text, welcome_msg.id, message_buttons))
        if captcha_status == 1:
            captcha_msg = await bot.send_message(event.chat_id, f"**{user_id}, click the button below to become verified!**",
                                                 buttons=[Button.url('CLICK ME!', url=config['BOT_LINK'])])
            await asyncio.sleep(60)
            try:
                await bot.delete_messages(event.chat_id, message_ids=[captcha_msg.id])
            except:
                pass
            query = db.insert(channel_table).values(msg_id=captcha_msg.id, msg_type="captcha", user_id=peer_user)
            connection.execute(query)


# Function for muting/unmuting users
@bot.on(events.NewMessage(from_users=admin_list))
async def mute_ban_function(event):
    try:
        event.peer_id.channel_id
    except AttributeError:
        return
    if event.reply_to is None:
        text = event.message.message
        if "unmute" in text:
            pass
        return
    unbanned = ChatBannedRights(
        until_date= None,
    )
    restricted = ChatBannedRights(
        until_date= None,
        send_messages=True,
        send_media=True,
        send_stickers=True,
        send_gifs=True,
        send_games=True,
        send_inline=True,
        embed_links=True
    )
    reply_msg = await bot(GetMessagesRequest(channel=event.peer_id.channel_id, id=[event.reply_to.reply_to_msg_id]))
    try:
        reply_user_id = reply_msg.messages[0].from_id.user_id

        replied_msg_text = event.message.message
        user = await bot.get_entity(reply_user_id)
        if not user.username and not user.last_name:
            user_id = user.first_name
        elif not user.username:
            user_id = user.first_name, user.last_name
        else:
            user_id = "@"+str(user.username)

        if "unmute" in replied_msg_text:
            unmuted_msg = await bot.send_message(event.chat_id, f"🔉 Unmuted {user_id}. 🔉\n")
            await bot(EditBannedRequest(event.chat_id, reply_user_id, unbanned))
            await asyncio.sleep(10)
            await bot.delete_messages(event.chat_id, message_ids=[unmuted_msg.id])
        elif "mute" in replied_msg_text:
            try:
                seconds = re.findall(r'[0-9]*[0-9]$', replied_msg_text)[0]
                muted_msg_text = f"🔇 Muted {user_id} for {seconds} seconds. 🔇\n"
                perm_mute = False
            except IndexError:
                muted_msg_text = f"🔇 Muted {user_id} forever! 🔇\n"
                seconds = 10
                perm_mute = True
            await bot(EditBannedRequest(event.chat_id, reply_user_id, restricted))
            muted_msg = await bot.send_message(event.chat_id, muted_msg_text)
            await asyncio.sleep(int(seconds))
            await bot.delete_messages(event.chat_id, message_ids=[muted_msg.id])
            if not perm_mute:
                unmuted_msg = await bot.send_message(event.chat_id, f"🔉 Unmuted {user_id}. 🔉\n")
                await bot(EditBannedRequest(event.chat_id, reply_user_id, unbanned))
                await asyncio.sleep(10)
                await bot.delete_messages(event.chat_id, message_ids=[unmuted_msg.id])
    except:
        no_msg = await bot.send_message(event.chat_id, f"Eh, no I'm not doing that...\n")

# Function for handling a banned word being sent
@bot.on(events.NewMessage(func=banned_word))
async def banned_words_func(event):
    if settings['banned_words']['enabled'] == 0:
        return
    max_warnings = settings['warnings']

    perm_banned = ChatBannedRights(
        until_date= None,
        view_messages=True,
    )
    restricted = ChatBannedRights(
        until_date=int(time())+60,
        send_messages=True,
        send_media=True,
        send_stickers=True,
        send_gifs=True,
        send_games=True,
        send_inline=True,
        embed_links=True
    )
    msg_id = event.id
    try:
        peer_user = event.original_update.message.peer_id.user_id
    except:
        peer_user = event.from_id.user_id
    if peer_user in admin_list:
        return
    user = await bot.get_entity(peer_user)
    await bot.delete_messages(event.chat_id, message_ids=[msg_id])
    if not user.username and not user.last_name:
        user_id = user.first_name
    elif not user.username:
        user_id = user.first_name, user.last_name
    else:
        user_id = "@"+str(user.username)
    search_query = db.select([users_table]).where(users_table.columns.peer_id == peer_user)
    ResultProxy = connection.execute(search_query)
    try:
        ResultSet = ResultProxy.fetchall()[0]
    except IndexError:
        query = db.insert(users_table).values(peer_id=peer_user)
        connection.execute(query)
        search_query = db.select([users_table]).where(users_table.columns.peer_id == peer_user)
        ResultProxy = connection.execute(search_query)
        ResultSet = ResultProxy.fetchall()[0]
    warning_count = int(ResultSet[1]) + 1
    if warning_count >= max_warnings:
        perm_ban_msg = await bot.send_message(event.chat_id, f"Enjoy your permanent ban {user_id}!")
        await asyncio.sleep(5)
        perm_ban = await bot(EditBannedRequest(event.chat_id, peer_user, perm_banned))
        await asyncio.sleep(10)
        await bot.delete_messages(event.chat_id, message_ids=[int(perm_ban.updates[0].id), perm_ban_msg.id])
    else:
        query = db.update(users_table).values(warnings=warning_count)
        query = query.where(users_table.columns.peer_id == peer_user)
        connection.execute(query)
        muted_msg = await bot.send_message(event.chat_id, f"You used a bad word {user_id}!\n"
                                              f"🔇 Muted for 60 seconds. 🔇\n"
                                              f"__Warning {warning_count} of {max_warnings}!__")
        await bot(EditBannedRequest(event.chat_id, peer_user, restricted))
        await asyncio.sleep(10)
        await bot.delete_messages(event.chat_id, message_ids=[muted_msg.id])


# Test function - Can be changed and used to run quick tests
@bot.on(events.NewMessage(pattern="/test"))
async def test(event):
    # message_buttons = []
    # buttons = project_presets['welcome_msg']['buttons']
    # for button in buttons:
    #     if buttons[button]:
    #         print(buttons[button])
    #         # print(buttons[button][1])
    #         if buttons[button][1]:
    #             # print(buttons[button][0], buttons[button][1])
    #             message_buttons.append([Button.url(text=buttons[button][0], url=buttons[button][1])])
    #
    # await bot.send_message(event.chat_id, "hi", buttons=message_buttons)
    pass


# Function for handling links/tg groups being sent
@bot.on(events.NewMessage(func=banned_links))
async def allowed_links_func(event):
    if settings['banned_links']['enabled'] == 0:
        return
    max_warnings = settings['warnings']
    message_text = event.message.message
    perm_banned = ChatBannedRights(
        until_date= None,
        view_messages=True,
    )
    try:
        peer_user = event.original_update.message.peer_id.user_id
    except:
        peer_user = event.from_id.user_id
    if peer_user in admin_list:
        return
    for tg in allowed_links_l:
        if tg.lower() in message_text.lower():
            return
    await bot.delete_messages(event.chat_id, message_ids=event.message.id)
    user = await bot.get_entity(peer_user)
    if not user.username and not user.last_name:
        user_id = user.first_name
    elif not user.username:
        user_id = user.first_name, user.last_name
    else:
        user_id = "@"+str(user.username)

    search_query = db.select([users_table]).where(users_table.columns.peer_id == peer_user)
    ResultProxy = connection.execute(search_query)
    try:
        ResultSet = ResultProxy.fetchall()[0]
    except IndexError:
        query = db.insert(users_table).values(peer_id=peer_user)
        connection.execute(query)
        search_query = db.select([users_table]).where(users_table.columns.peer_id == peer_user)
        ResultProxy = connection.execute(search_query)
        ResultSet = ResultProxy.fetchall()[0]
    warning_count = int(ResultSet[1]) + 1

    if warning_count >= max_warnings:
        perm_ban_msg = await bot.send_message(event.chat_id, f"Enjoy your permanent ban {user_id}!")
        await asyncio.sleep(5)
        perm_ban = await bot(EditBannedRequest(event.chat_id, peer_user, perm_banned))
        await asyncio.sleep(10)
        await bot.delete_messages(event.chat_id, message_ids=[int(perm_ban.updates[0].id), perm_ban_msg.id])
    else:
        query = db.update(users_table).values(warnings=warning_count)
        query = query.where(users_table.columns.peer_id == peer_user)
        connection.execute(query)
        not_allowed = await bot.send_message(event.chat_id, f"🚫 The link you sent is not allowed {user_id}!\n"
                                                            f"__Warning {warning_count} of {max_warnings}!__")
        await asyncio.sleep(10)
        await bot.delete_messages(event.chat_id, message_ids=[not_allowed.id])


# Function for timer on messages like captcha
async def message_timer(message_text, message_id, message_buttons=None):
    message_lines = message_text.split("\n")
    new_message = []
    for i in message_lines:
        seconds = re.findall(r"(.*)([0-9][0-9])( seconds.*)", i)
        if seconds:
            seconds = seconds[0]
            count = int(seconds[1])
            while count > 0:
                count -= 1
                combined_message = " ".join([str(item) for item in new_message])
                complete_message = f"{combined_message}{seconds[0]}{count}{seconds[2]}"
                await asyncio.sleep(1)
                await bot.edit_message(channel_id, message=message_id, text=complete_message, buttons=message_buttons)
            await bot.delete_messages(channel_id, message_ids=message_id)
        elif not seconds:
            new_message.append(i+"\n")


# Secret cat, meow
@bot.on(events.NewMessage(pattern="/cat"))
async def fun_cat(event):
    stickers_cats = await bot(GetStickerSetRequest(
        stickerset=InputStickerSetID(
            id=939064079232794628, access_hash=-8912556582100229719
        )
    ))
    await event.respond(file=stickers_cats.documents[random.randint(0, 119)])

# Secret dog, woof
@bot.on(events.NewMessage(pattern="/dog"))
async def fun_dog(event):
    stickers_dogs = await bot(GetStickerSetRequest(
        stickerset=InputStickerSetID(
            id=328774854541049858, access_hash=1718076299037790553
        )
    ))
    await event.respond(file=stickers_dogs.documents[random.randint(0, 41)])


# Secret vaultman, pls fix
@bot.on(events.NewMessage(pattern="/vaultman"))
async def fun_vman(event):
    quotes = ["wen next layer?", "dev fix price", "disable sell button", "dev burn more", "need more shill", "admin you burn too much tokens", "nox fix it", "too many tokens", "need more burn", "WHEN NEXT LAYER?"]
    await event.respond(quotes[random.randint(0, 9)])


# Function custom commands
@bot.on(events.NewMessage(func=custom_filter))
async def custom_command_send(event):
    if settings['custom_commands']['enabled'] == 0:
        return
    raw_message = event.message.message
    for key in custom_commands_names:
        if "@" in raw_message.lower():
            raw_message = re.findall(r"(.*)@", raw_message.lower())[0]
        if raw_message.lower() in key:
            command_key = key
    command = custom_commands_dict[command_key]
    send_message = command["message"]
    buttons = command["buttons"]
    files = command["files"]
    if buttons:
        button_list = []
        for button in buttons:
            button_list.append([Button.url(f'{buttons[button][0]}', url=f'{buttons[button][1]}')])
        await bot.send_message(event.chat_id, f'{send_message}', buttons=button_list)
        return
    if files:
        search_query = db.select([files_table]).where(files_table.columns.command == command_key)
        ResultProxy = connection.execute(search_query)
        ResultSet = ResultProxy.fetchall()
        await bot.send_message(event.chat_id, send_message)
        for i in ResultSet:
            file_to_send = i[3]
            file_to_send = pickle.loads(file_to_send)
            await bot.send_file(event.chat_id, file=file_to_send)
        return
    await bot.send_message(event.chat_id, send_message)


# Function help command
@bot.on(events.NewMessage(func=help_filter))
async def help_message(event):
    avail_commands = ""
    for key in custom_commands_names:
        avail_commands += f"{key} - {custom_commands_dict[f'{key}']['description']}\n"
    await event.respond(f"**Available Commands:**\n"
                        f"/price - Shows current RAV and RSHARE price.\n"
                        f"{avail_commands}"
                        f"__Note: You can use some commands with or without the /__")


@bot.on(events.NewMessage(func=fun_filter))
async def fun_response(event):
    stickers_cats = await bot(GetStickerSetRequest(
        stickerset=InputStickerSetID(
            id=939064079232794628, access_hash=-8912556582100229719
        )
    ))
    await event.respond(file=stickers_cats.documents[75])
    await event.respond(f"Just trying to help...")


# Function for new users verifying
@bot.on(events.NewMessage(pattern="/start"))
async def captcha(event):
    if isinstance(event.original_update, telethon.tl.types.UpdateNewMessage):
        unbanned = ChatBannedRights(
            until_date= None,
        )
        peer_user = event.original_update.message.peer_id.user_id
        search_query = db.select([users_table]).where(users_table.columns.peer_id == peer_user)
        ResultProxy = connection.execute(search_query)
        ResultSet = ResultProxy.fetchall()
        if not ResultSet[0]:
            query = db.insert(users_table).values(peer_id=peer_user)
            connection.execute(query)
        if not ResultSet[0][2]:
            captcha = await create_captcha()
            captcha_msg = await bot.send_message(event.chat_id, "**Type the captcha below to verify yourself!\n**")
            captcha_img = await bot.send_file(event.chat_id, filepath_captchas+"/"+captcha+".png")
            count = 60
            timer_msg = None
            loop = asyncio.get_running_loop()
            await_captcha_coro = loop.create_task(await_captcha(captcha, peer_user), name=f"new-captcha-{event.chat_id}")
            try:
                captcha_message_query = db.select([channel_table])
                CaptchaMsgProxy = connection.execute(captcha_message_query)
                CaptchaMsgSet = CaptchaMsgProxy.fetchall()
                captcha_channel_msg_id = CaptchaMsgSet[0][0]
            except:
                captcha_channel_msg_id = False
            while count >= 0:
                new_captcha_button = [Button.inline('New Captcha', f"new-captcha-{event.chat_id}")]
                if timer_msg is None:
                    timer_msg = await bot.send_message(event.chat_id, f"You have **{count}** seconds to solve the captcha or a new one will be generated.", buttons=new_captcha_button)
                else:
                    await bot.edit_message(event.chat_id, message=timer_msg.id, text=f"You have **{count}** seconds to solve the captcha or a new one will be generated.", buttons=new_captcha_button)
                await asyncio.sleep(1)
                search_query = db.select([users_table]).where(users_table.columns.peer_id == peer_user)
                ResultProxy = connection.execute(search_query)
                ResultSet = ResultProxy.fetchall()
                if ResultSet[0][2]:
                    await bot(EditBannedRequest(channel_id, peer_user, unbanned))
                    await bot.delete_messages(event.chat_id, message_ids=[timer_msg.id, captcha_msg.id, captcha_img.id])
                    await delete_captcha(captcha)
                    await bot.send_message(event.chat_id, f"Captcha solved! You can now return to the main chat!",
                                           buttons=[Button.url('Back To Chat', url="https://t.me/PulsarFarm")])
                    message_buttons = []
                    buttons = project_presets['resources']['buttons']
                    for button in buttons:
                        if buttons[button]:
                            if buttons[button][1]:
                                message_buttons.append([Button.url(text=buttons[button][0], url=buttons[button][1])])
                    await bot.send_message(event.chat_id, f"**{project_name} Resources**",
                                           buttons=message_buttons)
                    if captcha_channel_msg_id:
                        await bot.delete_messages(channel_id, message_ids=captcha_channel_msg_id)
                        delete_captcha_msg = channel_table.delete().where(channel_table.c.user_id == peer_user)
                        connection.execute(delete_captcha_msg)
                    break
                if count == 0:
                    await bot.send_message(event.chat_id, f"You failed to verify in time! Try again by typing /start")
                    await bot.delete_messages(event.chat_id, message_ids=[timer_msg.id, captcha_msg.id, captcha_img.id])
                    await delete_captcha(captcha)
                    if captcha_channel_msg_id:
                        await bot.delete_messages(channel_id, message_ids=captcha_channel_msg_id)
                        delete_captcha_msg = channel_table.delete().where(channel_table.c.user_id == peer_user)
                        connection.execute(delete_captcha_msg)
                    break
                if await_captcha_coro.done():
                    await bot.delete_messages(event.chat_id, message_ids=[timer_msg.id, captcha_msg.id, captcha_img.id])
                    await delete_captcha(captcha)
                    await bot.send_message(event.chat_id, f"Get a new captcha by typing /start")
                    if captcha_channel_msg_id:
                        await bot.delete_messages(channel_id, message_ids=captcha_channel_msg_id)
                        delete_captcha_msg = channel_table.delete().where(channel_table.c.user_id == peer_user)
                        connection.execute(delete_captcha_msg)
                    break
                count -= 1

        else:
            message_buttons = []
            buttons = project_presets['resources']['buttons']
            for button in buttons:
                if buttons[button]:
                    if buttons[button][1]:
                        message_buttons.append([Button.url(text=buttons[button][0], url=buttons[button][1])])
            await bot.send_message(event.chat_id, f"You're already verified and can use the {project_name} TG freely!",
                                   buttons=message_buttons)


# Function for awaiting captcha reply
async def await_captcha(captcha_text, peer_user):
    async with bot.conversation(peer_user) as conv:
        await_reply = conv.wait_event(events.NewMessage(pattern=captcha_text.upper()), timeout=40)
        await await_reply
        query = db.update(users_table).values(verified=True)
        query = query.where(users_table.columns.peer_id == peer_user)
        connection.execute(query)


# Function for creating captchas
async def create_captcha():
    image = ImageCaptcha(width = 160, height = 80)
    captcha_text = ''.join(random.choices(string.ascii_uppercase + string.digits, k = 6))
    img = image.write(captcha_text, filepath_captchas + "/" + captcha_text + '.png')
    return captcha_text


# Function for deleting captchas
async def delete_captcha(captcha_text):
    os.remove(filepath_captchas+"/"+captcha_text+".png")


# Function for catching the raw event, good for testing
@bot.on(events.Raw)
async def raw_test(event):
    print(f"\n------- RAW: --------\n{event.stringify()}\n------- END RAW --------\n")

# Function for showing admin panel
@bot.on(events.NewMessage(pattern="/admin"))
async def admin_panel(event):
    # First checks that it's not a channel
    try:
        event.peer_id.channel_id
        return
    except AttributeError:
        pass

    # Checks that the user is added to admin list
    if event.original_update.message.peer_id.user_id in admin_list:
        await bot.send_message(event.chat_id, "**🔷🔹🔷🔹🌟 ADMIN PANEL 🌟🔹🔷🔹🔷**",
                               buttons=admin_buttons)


# Function for showing admin panel
@bot.on(events.CallbackQuery(data=b'open-admin'))
async def admin_panel(event):
    # Checks that the user is added to admin list
    await bot.edit_message(event.query.user_id, message=event.query.msg_id, text="**🔷🔹🔷🔹🌟 ADMIN PANEL 🌟🔹🔷🔹🔷**", buttons=admin_buttons)


@bot.on(events.CallbackQuery(data=b'open-config'))
async def open_config(event):
    s_welcome = ("welcome", settings["welcome"]['enabled'])
    s_captcha = ("captcha", settings['captcha']['enabled'])
    s_banned_words = ("words", settings['banned_words']['enabled'])
    s_banned_links = ("links", settings['banned_links']['enabled'])
    s_banned_names = ("names", settings['banned_names']['enabled'])
    s_custom_commands = ("custom", settings['custom_commands']['enabled'])

    s_list = [s_welcome, s_captcha, s_banned_words, s_banned_links, s_banned_names, s_custom_commands]

    for s in s_list:
        if s[1] == 1:
            status = (s[0], "🟢 ENABLED")
        else:
            status = (s[0], "🔴 DISABLED")
        for i,v in enumerate(config_buttons):
            if s[0].lower() in v[0].text.lower():
                msg_text = re.findall(r"(.*:)", v[0].text)[0]
                v[0].text = f'{msg_text} {status[1]}'
                config_buttons.pop(i)
                config_buttons.insert(i, [v[0]])
                continue

    edited_msg = await bot.edit_message(event.query.user_id, message=event.query.msg_id, buttons=config_buttons)

# Function for sending message to anyone who has interacted with the bot, like an announcement.
@bot.on(events.NewMessage(pattern="/broadcast"))
async def broadcast(event):
    # Can only be used by admins, type "/broadcast your message here" to send
    if event.original_update.message.peer_id.user_id in admin_list:
        search_query = db.select([users_table.columns.peer_id])
        ResultProxy = connection.execute(search_query)
        ResultSet = ResultProxy.fetchall()
        peer_list = []
        for peers in ResultSet:
            peers = str(peers).replace(",", "")
            peers = str(peers).replace("(", "")
            peers = str(peers).replace(")", "")
            peer_list.append(int(peers))
        broadcast_message = re.findall(r'(/broadcast).(.*)', event.message.message)
        broadcast_message = broadcast_message[0]
        for user in peer_list:
            try:
                await bot.send_message(user, f"{broadcast_message[1]}")
            except:
                pass


# Start the bot
if __name__ == "__main__":
    bot.run_until_disconnected()

