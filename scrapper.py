from logging import error
import math
import os
import requests
import re
import time
import traceback
from urllib.parse import urlsplit

from bs4 import BeautifulSoup as BS
from flask import Flask, request
import telebot
from telebot import types

# # Establishing connection
# boto.set_stream_logger('boto')
# s3 = S3Connection(os.environ['SECRET_BOT'])

# rs = s3.get_all_buckets()
# for bucket in rs:
#     print(f'Name:{bucket.name}')
#     print(f'Keys: {bucket.list()}')
    

# s3.create_bucket('HEROKU_ENV_VARS_OLX_BOT', location=Location.EUCentral1)


TOKEN_BOT = os.environ.get('SECRET_BOT')
print(TOKEN_BOT)
bot = telebot.TeleBot(TOKEN_BOT, parse_mode='html')
server = Flask(__name__)

user_dict = {}
target_districts = ['Ursynów', 'Mokotów', 'Wola', 'Śródmieście']


class Offer:
    def __init__(self, link, district):
        self.link = link
        self.district = district
        self.id = None
        self.date = None


class User:
    def __init__(self):
        self.arr_str = None
        self.arr_markup = None
        self.start_page = 1
        self.pages_amount = 3
        self.max_price = 3250


@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "Use /offers command to get offers")


def grab(link):
    r = requests.get(link)
    html = BS(r.content, 'html.parser')
    return html


def is_number(n):
    try:
        float(n)
        return True
    except ValueError:
        return False


def extractor(price_str, czynsz_str):
    price = int(re.sub(r'\s|zł', '', price_str))

    czynsz = ''.join([x for x in czynsz_str.replace(
        ',', '.').split() if is_number(x)])
    czynsz = int(float(czynsz))

    return [price, czynsz if czynsz > 1 else 0]


def pages_total():
    pages_total = grab(
        f"https://www.olx.pl/nieruchomosci/mieszkania/wynajem/warszawa/?search%5Bfilter_enum_rooms%5D%5B0%5D=three")
    last_page = pages_total.select('.pager')[0]
    last_page = last_page.find(
        'a', {'data-cy': "page-link-last"}).find('span').text
    return last_page


def grab_offers(process_msg):
    offer_dict = []
    user = user_dict[process_msg.chat.id]
    pages_amount = user.pages_amount
    start_page = user.start_page

    last_page = start_page + pages_amount - 1

    for page_num in range(start_page, int(last_page) + 1):
        bot.edit_message_text(
            f'Page number: {page_num}/{last_page}',
            process_msg.chat.id,
            process_msg.message_id)
        print(f'Page number: {page_num}/{last_page}')
        html = grab(
            f"https://www.olx.pl/nieruchomosci/mieszkania/wynajem/warszawa/?search%5Bfilter_enum_rooms%5D%5B0%5D=three&page={page_num}")
        items = html.select(".wrap")

        for elem in items:
            link = elem.find('a')['href']
            date = elem.find('i', {"data-icon": "clock"}).next_sibling
            district = elem.find(
                'td', {'class': 'bottom-cell'}).find('span').text
            try:
                district = district.split()[1]
            except BaseException:
                pass
            if (district in target_districts):
                offer = Offer(link, district)
                if urlsplit(link).netloc == 'www.otodom.pl':
                    id = elem.find('table')['data-id']
                    offer.id = id
                offer.date = date
                offer_dict.append(offer)
    bot.edit_message_text(f'Offers grabbed...',
                          process_msg.chat.id, process_msg.message_id)
    return offer_dict


def grab_offer_content(offer_dict, process_msg):
    proper_offers = []
    c = 1
    for item in offer_dict:
        html = grab(item.link)
        price = 0
        czynsz = 0
        description_str = ''
        site = ''

        print(f'Offer {c}/{len(offer_dict)}')
        bot.edit_message_text(
            f'Skanning offers {c}/{len(offer_dict)}',
            process_msg.chat.id,
            process_msg.message_id)
        c += 1
        try:
            if urlsplit(item.link).netloc == 'www.otodom.pl':
                # Parsing html
                site = 'Otodom'
                price_str = html.find('strong', {'aria-label': "Cena"}).text
                czynsz_elem_wrap = html.find(
                    'div', {'aria-label': 'Czynsz - dodatkowo'})
                description_str_arr = html.find(
                    'div', {'data-cy': "adPageAdDescription"}).select('p')
                description_str = ''
                for i in description_str_arr:
                    description_str += i.text

                if czynsz_elem_wrap is not None:
                    czynsz_str = czynsz_elem_wrap.select('div')[1].text
                    # extracting price, czynsz numbers
                    price, czynsz = extractor(price_str, czynsz_str)
                else:
                    price, czynsz = extractor(price_str, '0')
            else:
                # Parsing html
                site = 'Olx'
                czynsz_str = html.find('ul').select('li')[-1].find('p').text
                price_str = html.select('h3')[0].text
                description_str = html.find(
                    'div', {'data-cy': "ad_description"}).find('div').text
                id = html.find(
                    'div', {
                        "data-cy": "ad-footer-bar-section"}).select('span')[0].text.split()[1]

                # extracting price, czynsz numbers
                price, czynsz = extractor(price_str, czynsz_str)
            if price + czynsz < user_dict[process_msg.chat.id].max_price:
                offer = Offer(item.link, item.district)

                offer.site = site
                offer.id = id if (item.id is None) else item.id
                offer.price = price
                offer.czynsz = czynsz
                offer.description = description_str
                offer.date = item.date

                proper_offers.append(offer)

        except Exception:
            print(price_str, czynsz_str)
            print(item.link)
            print(traceback.format_exc())
            continue

    return proper_offers


def main(process_msg):
    offer_dict = grab_offers(process_msg)
    proper_offers = grab_offer_content(offer_dict, process_msg)
    return proper_offers


@bot.message_handler(commands=['offers'])
def info_grabbing(message):
    user_dict[message.chat.id] = User()
    user_dict[message.chat.id].message_id = message.chat.id

    desc_str = f'<b>Выбрать параметры запуска:</b>\n-----------------------\n<b>Дефолтные:</b> 3 страницы, начиная с первой (обычно это все объявления за последний день) \n\n <b>Кастомные:</b> можно выбрать начальную страницу и кол-во страниц от начальной \n\n <i> Общее кол-во страниц: </i>'

    mark_up_mode = types.InlineKeyboardMarkup()
    item1 = types.InlineKeyboardButton(
        text='Default', callback_data='default')
    item2 = types.InlineKeyboardButton(
        text='Custom', callback_data='custom')
    mark_up_mode.add(item1, item2)

    msg_mode = bot.send_message(
        message.chat.id, desc_str, reply_markup=mark_up_mode)
    user_dict[message.chat.id].msg_mode = msg_mode


def start_grabbing(message, custom_mode=False):
    user = user_dict[message.chat.id]
    try:
        bot.delete_message(user.msg_mode.chat.id,
                           user.msg_mode.message_id)
    except error:
        print(error)

    # Sending main message
    process_msg = bot.send_message(message.chat.id, 'Grabbing data...')
    user_dict[message.chat.id].process_msg = process_msg
    # Setting parameters for default mode if chosen
    if not custom_mode:
        user.start_page = 1
        user.pages_amount = 3
        user.max_price = 3250
    # Getting offers list
    offers_dict = main(process_msg)
    # Turning on slider
    strsq(message, offers_dict)
    # Sending message with slider
    bot.edit_message_text(user_dict[message.chat.id].arr_str[0],
                          process_msg.chat.id,
                          process_msg.message_id,
                          reply_markup=user_dict[message.chat.id].arr_markup[0],
                          disable_web_page_preview=True)


def strsq(message, records):
    str_per_page = 10
    x = math.ceil((len(records)) / str_per_page)

    arr_str = []
    arr_markup = []
    for i in range(x):
        arr_str.append('')
        arr_markup.append('')

    if len(records) == 0:
        arr_str.append(
            '--------------------------------\nПозиции отсутсвуют\n--------------------------------')
        arr_markup.append('')

    user = user_dict[message.chat.id]
    end_page = user.start_page + user.pages_amount

    arr_str[0] += f'Pages: <b>{user.pages_amount}</b> ({user.start_page} to {end_page}). Offers: <b>{len(records)}</b>\n'
    counter = 0
    ind = 0
    for row in records:
        counter += 1
        if counter > (
                str_per_page * ind) and counter <= (str_per_page * (ind + 1)):
            arr_str[ind] += f'<a href="{row.link}">[Offer {counter}]</a> <i>({row.date})</i>\nID: <b>{row.id}</b>. Price: <b>{row.price + row.czynsz}</b>. District: <b>{row.district}</b>\n'
            arr_str[ind] += '--------------------------------\n'
        else:
            ind += 1
            arr_str[ind] += f'<a href="{row.link}">[Offer {counter}]</a>. <i>({row.date})</i>\nID: <b>{row.id}</b>. Price: <b>{row.price + row.czynsz}</b>. District: <b>{row.district}</b>\n'
            arr_str[ind] += '--------------------------------\n'

    for i in range(len(arr_markup)):
        if i == 0 and len(records) <= 10:
            mark_up_pos = types.InlineKeyboardMarkup(row_width=1)
            item1 = types.InlineKeyboardButton(
                text=f'{i+1} of {len(arr_markup)}', callback_data=f'{i}of')
            item2 = types.InlineKeyboardButton(
                text=f'↩', callback_data=f'back_main')
            mark_up_pos.add(item1, item2)
        elif i == 0:
            mark_up_pos = types.InlineKeyboardMarkup(row_width=2)
            item1 = types.InlineKeyboardButton(
                text=f'{i+1} of {len(arr_markup)}', callback_data=f'{i}of')
            item2 = types.InlineKeyboardButton(
                text=f'→', callback_data=f'{i}>')
            item3 = types.InlineKeyboardButton(
                text=f'↩', callback_data=f'back_main')
            mark_up_pos.add(item1, item2, item3)
        elif i != 0 and i != (len(arr_markup) - 1):
            mark_up_pos = types.InlineKeyboardMarkup(row_width=3)
            item1 = types.InlineKeyboardButton(
                text=f'←', callback_data=f'<{i}')
            item2 = types.InlineKeyboardButton(
                text=f'{i+1} of {len(arr_markup)}', callback_data=f'{i}of')
            item3 = types.InlineKeyboardButton(
                text=f'→', callback_data=f'{i}>')
            item4 = types.InlineKeyboardButton(
                text=f'↩', callback_data=f'back_main')
            mark_up_pos.add(item1, item2, item3, item4)
        else:
            mark_up_pos = types.InlineKeyboardMarkup(row_width=2)
            item1 = types.InlineKeyboardButton(
                text=f'←', callback_data=f'<{i}')
            item2 = types.InlineKeyboardButton(
                text=f'{i+1} of {len(arr_markup)}', callback_data=f'{i}of')
            item3 = types.InlineKeyboardButton(
                text=f'↩', callback_data=f'back_main')
            mark_up_pos.add(item1, item2, item3)

        arr_markup[i] = mark_up_pos

    user_dict[message.chat.id].arr_str = arr_str
    user_dict[message.chat.id].arr_markup = arr_markup


@bot.callback_query_handler(func=lambda call: True)
def start_callback(call):
    if call.data:
        # 'arr_markup' in globals():
        if re.match(r'^\dof$|^<\d$|^\d>$', call.data):
            arr_str = user_dict[call.message.chat.id].arr_str
            arr_markup = user_dict[call.message.chat.id].arr_markup
            msg_str = user_dict[call.message.chat.id].process_msg
            for i in range(len(arr_markup)):
                if call.data == f'{i}>':
                    try:
                        bot.edit_message_text(arr_str[i + 1],
                                              call.message.chat.id,
                                              msg_str.message_id,
                                              reply_markup=arr_markup[i + 1],
                                              disable_web_page_preview=True)
                    except BaseException:
                        pass
                if call.data == f'<{i}':
                    try:
                        bot.edit_message_text(arr_str[i - 1],
                                              call.message.chat.id,
                                              msg_str.message_id,
                                              reply_markup=arr_markup[i - 1],
                                              disable_web_page_preview=True)
                    except BaseException:
                        pass
                if call.data == f'{i}of':
                    bot.answer_callback_query(
                        call.id, f'{i+1} of {len(arr_markup)}', show_alert=True)
        if call.data == 'default':
            start_grabbing(call.message)
        if call.data == 'custom':
            custom_mode(call.message)

        if call.data == 'pages':
            total_pages = user_dict[call.message.chat.id].total_pages
            param_pages_msg = bot.edit_message_text(
                f'Введите <b>Начальную страницу:</b> и <b>Кол-во страниц:</b>\n------------------\nПример: "3 1" \n(3 - начальная страница, 1 - кол-во)\n------------------\n<i>Общее кол-во страниц: <b>{total_pages}</b>\nНачальная страница + кол-во страниц не должно превышать <b>{total_pages}</b></i>',
                user_dict[
                    call.message.chat.id].msg_mode.chat.id,
                user_dict[
                    call.message.chat.id].msg_mode.message_id,
                reply_markup=None)
            bot.register_next_step_handler(param_pages_msg, param_pages)
        if call.data == 'price':
            param_pages_msg = bot.edit_message_text('Введите <b>Цену</b>:',
                                                    user_dict[call.message.chat.id].msg_mode.chat.id,
                                                    user_dict[call.message.chat.id].msg_mode.message_id,
                                                    reply_markup=None)
            bot.register_next_step_handler(param_pages_msg, param_price)
        if call.data == 'go_custom':
            start_grabbing(call.message, True)
        if call.data == 'back_main':
            try:
                bot.delete_message(
                    call.message.chat.id, user_dict[call.message.chat.id].process_msg.message_id)
            except BaseException:
                pass
            try:
                bot.delete_message(call.message.chat.id,
                                   user_dict[call.message.chat.id].msg_mode.message_id)
            except BaseException:
                pass
            info_grabbing(call.message)


def custom_mode(message):
    user = user_dict[message.chat.id]

    mark_up_custom = types.InlineKeyboardMarkup(row_width=3)
    item1 = types.InlineKeyboardButton(
        text='Edit Pages', callback_data='pages')
    item2 = types.InlineKeyboardButton(
        text='Edit Price', callback_data='price')
    item3 = types.InlineKeyboardButton(
        text='Start grabbing', callback_data='go_custom')
    item4 = types.InlineKeyboardButton(
        text=f'↩', callback_data=f'back_main')
    mark_up_custom.add(item1, item2, item3, item4)

    info_str = f'''
    <b>Установленные параметры:</b>
    -----------------------------
    Начальная страница: <b>{user.start_page}</b>\n
    Кол-во страниц: <b>{user.pages_amount}</b>\n
    Максимальная цена: <b>{user.max_price}</b>\n\n
    <i>Нажмите "Start grabbing" чтобы запустить парсер с этими параметрами</i>
    '''

    bot.edit_message_text(
        info_str,
        user.msg_mode.chat.id,
        user.msg_mode.message_id,
        reply_markup=mark_up_custom)


def param_pages(message):
    print(message.text)
    if re.match(r"^\d{1,2}\s\d{1,2}$", message.text):
        start_page = int(message.text.split(' ')[0])
        pages_amount = int(message.text.split(' ')[1])
        if start_page + pages_amount - \
                1 <= int(user_dict[message.chat.id].total_pages):
            user_dict[message.chat.id].start_page = start_page
            user_dict[message.chat.id].pages_amount = pages_amount

            custom_mode(message)
            return

    bot.edit_message_text('Wrong input, going back to parametrs...',
                          user_dict[message.chat.id].msg_mode.chat.id,
                          user_dict[message.chat.id].msg_mode.message_id)
    time.sleep(1)
    custom_mode(message)


def param_price(message):
    if re.match(r"^\d+$", message.text):
        if int(message.text) > 1500 and int(message.text) < 8000:
            user_dict[message.chat.id].max_price = int(message.text)
            custom_mode(message)
            return
    bot.edit_message_text('Wrong input, going back to parametrs...',
                          user_dict[message.chat.id].msg_mode.chat.id,
                          user_dict[message.chat.id].msg_mode.message_id)
    time.sleep(1)
    custom_mode(message)

@server.route('/' + TOKEN_BOT, methods=['POST'])
def getMessage():
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return "!", 200


@server.route("/")
def webhook():
    bot.remove_webhook()
    bot.set_webhook(url='https://olx-flat-parser.herokuapp.com/' + TOKEN_BOT)
    return "!", 200


if __name__ == "__main__":
    server.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)))