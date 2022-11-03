import io
import json
import urllib
from glob import glob

import numpy as np
from tensorflow.keras.models import load_model
import tensorflow as tf
import tensorflow_addons as tfa
from PIL import Image, ImageOps
from flask import Flask, request, abort
# from flask_ngrok import run_with_ngrok

from linebot import (
    LineBotApi, WebhookHandler
)
from linebot.exceptions import (
    InvalidSignatureError
)
from linebot.models import (
    FollowEvent, MessageEvent, PostbackEvent,
    TextMessage, ImageMessage,
    TextSendMessage, ImageSendMessage
)
from linebot.models import (
    MessageAction, URIAction,
    PostbackAction, DatetimePickerAction,
    CameraAction, CameraRollAction, LocationAction,
    QuickReply, QuickReplyButton
)

from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
import pytz

# 讀取模型
model = load_model("/content/drive/MyDrive/generator_v2.h5")
# # 設定分類模型label
all_class = ['正常的龜背芋', '根爛或老化', '曬傷', '病菌感染', '其他植物']

# 建立Flask框架 (http server)
app = Flask(__name__, static_url_path = "/material" , static_folder = "./material/")
# run_with_ngrok(app)

# 設定line_bot_api資訊
# line_bot_api = LineBotApi('Btz6xnIBTrcc8lUlz9NOc0Q4/JpWNq0/SVLZ+GJWMUdo/YExOzFX2+gZ+ITe+S7Cr4LxSHsKfNy/3D1CjABRKDN9gR+vkvAc0oQvwZnp8HcJZsji1y5KcHsuLwLhLKlz7NgtQob+XpLgIsCdbmRSkAdB04t89/1O/w1cDnyilFU=')
# handler = WebhookHandler('17b14650c110f87ad15c98edaaf49c0b')
line_bot_api = LineBotApi('3v0P0QKM6SK5EtmW4tyzBZRgbenxgXjm9zNvPDvgOYZJRN/Z7gDp76rhOIMO/v/qmlZf6XFQGBlBC0v5sYPxcfU1JPl3i7ruOGNLn94HZgJZtnZbTojfwGANyD0Dy9rCNIH2HFXSYE9C90DMLsyjVAdB04t89/1O/w1cDnyilFU=')
handler = WebhookHandler('79bffdb9e50e19336e79aad0679665fc')

# 設定時區
taiwan_tz = pytz.timezone('Asia/Taipei')

# 啟動API接口
@app.route("/callback", methods=['POST'])
def callback():
    # get X-Line-Signature header value
    # 取得Line的加密簽章：每則傳來的消息都有一個加密簽章
    signature = request.headers['X-Line-Signature']

    # get request body as text
    # 取得body:用戶傳來的內容
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    # 記錄用戶log
    # 存在google drive的ai-event.log
    f = open("ai-event.log", "a")
    f.write(body)
    f.close()

    # handle webhook body
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("Invalid signature. Please check your channel access token/channel secret.")
        abort(400)

    return 'OK'

# 告知handler，如果收到FollowEvent，則做下面的方法處理
# @handler.add(FollowEvent)
# def reply_text_and_get_user_profile(event):
    # 取出消息內User的資料
    # 用line_bot_api跟Line溝通，用get_profile(event.source.user_id)取得個資
    # event: 每一次傳來的消息；source: 來源；user_id: 發消息的用戶id
    # user_profile = line_bot_api.get_profile(event.source.user_id)

    # 將用戶資訊存在檔案內
    # 存在google drive的users.txt
    # with open("users.txt", "a") as myfile:
    #     myfile.write(json.dumps(vars(user_profile), sort_keys=True))
    #     myfile.write('\n')

    # TODO: 將用戶資料存到gcp firestore
    # 跟line 取回照片，並放置在本地端
    # file_name = user_profile.user_id + '.jpg'
    # urllib.request.urlretrieve(user_profile.picture_url, file_name)

    # 設定內容
    # storage_client = storage.Client()
    # bucket_name="YOUR-BUCKET-NAME"
    # destination_blob_name=f"{user_profile.user_id}/user_pic.png"
    # source_file_name=file_name

    # 進行上傳
    # bucket = storage_client.bucket(bucket_name)
    # blob = bucket.blob(destination_blob_name)
    # blob.upload_from_filename(source_file_name)

    # # 設定用戶資料json
    # user_dict={
    #   "user_id":user_profile.user_id,
    #   "picture_url": f"https://storage.googleapis.com/{bucket_name}/{destination_blob_name}",
    #   "display_name": user_profile.display_name,
    #   "status_message": user_profile.status_message
    # }
    # # 插入firestore
    # db = firestore.Client()
    # doc_ref = db.collection(u'line-user').document(user_dict.get("user_id"))
    # doc_ref.set(user_dict)

# 讀取圖片後的動作模式(預設="record")
pic_mode = "record"

# AI分類模型
def classify(img):
    img = ImageOps.fit(img, model.input.shape[1:3])
    img = np.expand_dims(img, axis=0)
    img = tf.keras.applications.efficientnet_v2.preprocess_input(img, data_format=None)
    prediction = model.predict(img)[0]
    return all_class[prediction.argmax(axis=-1)]

# 植栽設定的各項參數
# 參數名
plant_params_list = ["植物外觀", "植物環境", "照顧時程", "盆栽位置", "盆器設定"]
plant_profile = {
    "植物高度":"",
    "植物年齡":""
}
plant_env = {
    "環境溫度":"",
    "環境通風程度":""
}
takecare_plant = {
    "澆水頻率":"",
    "施肥頻率":""
}
pot_site = {
    "種植空間":"",
    "環境光線":""
}
pot_setting = {
    "盆器材質":"",
    "排水孔":""
}

# 設定各項參數的quickreply
# "植物外觀"："植物高度"、"植物年齡"
# "植物高度": "迷你龜"、"小龜"、"中龜"、"大龜"、"巨龜"
tinyplant_QuickReplyButton = QuickReplyButton(
    action=MessageAction(
        label="迷你龜",
        text="迷你龜"
    )
)
smallplant_QuickReplyButton = QuickReplyButton(
    action=MessageAction(
        label="小龜",
        text="小龜"
    )
)
middleplant_QuickReplyButton = QuickReplyButton(
    action=MessageAction(
        label="中龜",
        text="中龜"
    )
)
largeplant_QuickReplyButton = QuickReplyButton(
    action=MessageAction(
        label="大龜",
        text="大龜"
    )
)
giantplant_QuickReplyButton = QuickReplyButton(
    action=MessageAction(
        label="巨龜",
        text="巨龜"
    )
)
plant_hight_ReplyList = QuickReply(
    items = [tinyplant_QuickReplyButton, smallplant_QuickReplyButton,
        middleplant_QuickReplyButton,   largeplant_QuickReplyButton,
        giantplant_QuickReplyButton]
)
plant_hight_List = ["迷你龜", "小龜", "中龜", "大龜", "巨龜"]

# "植物年齡": "一年以下"、"一至三年"、"三年以上"
lower_one_year_QuickReplyButton = QuickReplyButton(
    action=MessageAction(
        label="一年以下",
        text="一年以下"
    )
)
onetothree_year_QuickReplyButton = QuickReplyButton(
    action=MessageAction(
        label="一至三年",
        text="一至三年"
    )
)
upper_three_year_QuickReplyButton = QuickReplyButton(
    action=MessageAction(
        label="三年以上",
        text="三年以上"
    )
)
plant_age_ReplyList = QuickReply(
    items = [lower_one_year_QuickReplyButton,
          onetothree_year_QuickReplyButton,
          upper_three_year_QuickReplyButton]
)
plant_age_List = ["一年以下", "一至三年", "三年以上"]

# "植物環境": "環境溫度"、"環境通風程度"
# "環境溫度": "炎熱"、"溫暖"、"適中"、"涼爽"、"寒冷"
hot_QuickReplyButton = QuickReplyButton(
    action=MessageAction(
        label="炎熱",
        text="炎熱"
    )
)
warm_QuickReplyButton = QuickReplyButton(
    action=MessageAction(
        label="溫暖",
        text="溫暖"
    )
)
well_temp_QuickReplyButton = QuickReplyButton(
    action=MessageAction(
        label="適中",
        text="適中"
    )
)
cool_QuickReplyButton = QuickReplyButton(
    action=MessageAction(
        label="涼爽",
        text="涼爽"
    )
)
cold_QuickReplyButton = QuickReplyButton(
    action=MessageAction(
        label="寒冷",
        text="寒冷"
    )
)

plant_env_temp_ReplyList = QuickReply(
    items = [hot_QuickReplyButton,
          warm_QuickReplyButton,
          well_temp_QuickReplyButton,
          cool_QuickReplyButton,
          cold_QuickReplyButton]
)
plant_env_temp_List = ["炎熱", "溫暖", "適中", "涼爽", "寒冷"]

# "環境通風程度": 通風舒適 不通風
wind_QuickReplyButton = QuickReplyButton(
    action=MessageAction(
        label="通風舒適",
        text="通風舒適"
    )
)
unwind_QuickReplyButton = QuickReplyButton(
    action=MessageAction(
        label="不通風",
        text="不通風"
    )
)

plant_env_wind_ReplyList = QuickReply(
    items = [wind_QuickReplyButton,
          unwind_QuickReplyButton]
)
plant_env_wind_List = ["通風舒適", "不通風"]

# "照顧時程": "澆水頻率"、"施肥頻率"
# "澆水頻率": 0-3天、3-7天、7-10天、10天以上
water_three_QuickReplyButton = QuickReplyButton(
    action=MessageAction(
        label="0-3天",
        text="0-3天"
    )
)
water_threetoseven_QuickReplyButton = QuickReplyButton(
    action=MessageAction(
        label="3-7天",
        text="3-7天"
    )
)
water_seventoten_QuickReplyButton = QuickReplyButton(
    action=MessageAction(
        label="7-10天",
        text="7-10天"
    )
)
water_ten_up_QuickReplyButton = QuickReplyButton(
    action=MessageAction(
        label="10天以上",
        text="10天以上"
    )
)

watering_freq_ReplyList = QuickReply(
    items = [water_three_QuickReplyButton,
          water_threetoseven_QuickReplyButton,
          water_seventoten_QuickReplyButton,
          water_ten_up_QuickReplyButton]
)
watering_freq_List = ["0-3天", "3-7天", "7-10天", "10天以上"]

# "施肥頻率": 一個月內、1-2個月、3-4個月、5個月以上
fertilize_onemonth_QuickReplyButton = QuickReplyButton(
    action=MessageAction(
        label="一個月內",
        text="一個月內"
    )
)
fertilize_onetotwomonth_QuickReplyButton = QuickReplyButton(
    action=MessageAction(
        label="1-2個月",
        text="1-2個月"
    )
)
fertilize_threetofourmonth_QuickReplyButton = QuickReplyButton(
    action=MessageAction(
        label="3-4個月",
        text="3-4個月"
    )
)
fertilize_fivemonth_up_QuickReplyButton = QuickReplyButton(
    action=MessageAction(
        label="5個月以上",
        text="5個月以上"
    )
)

fertilize_freq_ReplyList = QuickReply(
    items = [fertilize_onemonth_QuickReplyButton,
          fertilize_onetotwomonth_QuickReplyButton,
          fertilize_threetofourmonth_QuickReplyButton,
          fertilize_fivemonth_up_QuickReplyButton]
)
fertilize_freq_List = ["一個月內", "1-2個月", "3-4個月", "5個月以上"]

# "盆栽位置": "種植空間"、"環境光線"
# "種植空間": 臥室、客廳、辦公室、洗手間、玄關、庭院、陽台、其他室內、其他室外
bedroom_QuickReplyButton = QuickReplyButton(
    action=MessageAction(
        label="臥室",
        text="臥室"
    )
)
livingroom_QuickReplyButton = QuickReplyButton(
    action=MessageAction(
        label="客廳",
        text="客廳"
    )
)
office_QuickReplyButton = QuickReplyButton(
    action=MessageAction(
        label="辦公室",
        text="辦公室"
    )
)
restroom_QuickReplyButton = QuickReplyButton(
    action=MessageAction(
        label="洗手間",
        text="洗手間"
    )
)
entrance_QuickReplyButton = QuickReplyButton(
    action=MessageAction(
        label="玄關",
        text="玄關"
    )
)
garden_QuickReplyButton = QuickReplyButton(
    action=MessageAction(
        label="庭院",
        text="庭院"
    )
)
balcony_QuickReplyButton = QuickReplyButton(
    action=MessageAction(
        label="陽台",
        text="陽台"
    )
)
inside_QuickReplyButton = QuickReplyButton(
    action=MessageAction(
        label="其他室內",
        text="其他室內"
    )
)
outside_QuickReplyButton = QuickReplyButton(
    action=MessageAction(
        label="其他室外",
        text="其他室外"
    )
)

plantspace_ReplyList = QuickReply(
    items = [bedroom_QuickReplyButton, livingroom_QuickReplyButton,
            office_QuickReplyButton, restroom_QuickReplyButton,
             entrance_QuickReplyButton, garden_QuickReplyButton,
             balcony_QuickReplyButton, inside_QuickReplyButton,
             outside_QuickReplyButton]
)
plantspace_List = ["臥室", "客廳", "辦公室", "洗手間", "玄關" "庭院", "陽台" "其他室內" "其他室外"]

# "環境光線": 明亮直射、明亮散射、半陰暗環境、無自然光線
straightbright_light_QuickReplyButton = QuickReplyButton(
    action=MessageAction(
        label="明亮直射",
        text="明亮直射"
    )
)
scatteredbright_light_QuickReplyButton = QuickReplyButton(
    action=MessageAction(
        label="明亮散射",
        text="明亮散射"
    )
)
helflight_light_QuickReplyButton = QuickReplyButton(
    action=MessageAction(
        label="半陰暗環境",
        text="半陰暗環境"
    )
)
dark_light_QuickReplyButton = QuickReplyButton(
    action=MessageAction(
        label="無自然光線",
        text="無自然光線"
    )
)
light_ReplyList = QuickReply(
    items = [straightbright_light_QuickReplyButton,
             scatteredbright_light_QuickReplyButton,
             helflight_light_QuickReplyButton,
             dark_light_QuickReplyButton]
)
light_List = ["明亮直射", "明亮散射", "半陰暗環境", "無自然光線"]

# "盆器設定": "盆器材質"、"排水孔"
# "盆器材質": 陶土盆器、塑膠盆器、瓷製盆器、玻璃盆器、水泥盆器、泥炭盆器、金屬盆器、石製盆器、木製盆器
clay_pot_QuickReplyButton = QuickReplyButton(
    action=MessageAction(
        label="陶土盆器",
        text="陶土盆器"
    )
)
plastic_pot_QuickReplyButton = QuickReplyButton(
    action=MessageAction(
        label="塑膠盆器",
        text="塑膠盆器"
    )
)
ceramics_pot_QuickReplyButton = QuickReplyButton(
    action=MessageAction(
        label="瓷製盆器",
        text="瓷製盆器"
    )
)
glass_pot_QuickReplyButton = QuickReplyButton(
    action=MessageAction(
        label="玻璃盆器",
        text="玻璃盆器"
    )
)
cement_pot_QuickReplyButton = QuickReplyButton(
    action=MessageAction(
        label="水泥盆器",
        text="水泥盆器"
    )
)
peat_pot_QuickReplyButton = QuickReplyButton(
    action=MessageAction(
        label="泥炭盆器",
        text="泥炭盆器"
    )
)
metal_pot_QuickReplyButton = QuickReplyButton(
    action=MessageAction(
        label="金屬盆器",
        text="金屬盆器"
    )
)
stone_pot_QuickReplyButton = QuickReplyButton(
    action=MessageAction(
        label="石製盆器",
        text="石製盆器"
    )
)
wood_pot_QuickReplyButton = QuickReplyButton(
    action=MessageAction(
        label="木製盆器",
        text="木製盆器"
    )
)

pot_material_ReplyList = QuickReply(
    items = [clay_pot_QuickReplyButton, plastic_pot_QuickReplyButton,
             ceramics_pot_QuickReplyButton, glass_pot_QuickReplyButton,
             cement_pot_QuickReplyButton, peat_pot_QuickReplyButton,
             metal_pot_QuickReplyButton, stone_pot_QuickReplyButton,
             wood_pot_QuickReplyButton]
)
pot_material_List = ["陶土盆器", "塑膠盆器", "瓷製盆器", "玻璃盆器", "水泥盆器", "泥炭盆器", "金屬盆器", "石製盆器", "木製盆器"]

# "排水孔": 是、否
drainagehole_y_QuickReplyButton = QuickReplyButton(
    action=MessageAction(
        label="有",
        text="有"
    )
)
drainagehole_n_QuickReplyButton = QuickReplyButton(
    action=MessageAction(
        label="沒有",
        text="沒有"
    )
)

drainagehole_ReplyList = QuickReply(
    items = [drainagehole_y_QuickReplyButton, drainagehole_n_QuickReplyButton]
)
drainagehole_List = ["有", "沒有"]

Show_plant_profile = f'''{plant_params_list[0]}
  {list(plant_profile.keys())[0]}:{list(plant_profile.values())[0]}
  {list(plant_profile.keys())[1]}:{list(plant_profile.values())[1]}\n
{plant_params_list[1]}
  {list(plant_env.keys())[0]}:{list(plant_env.values())[0]}
  {list(plant_env.keys())[1]}:{list(plant_env.values())[1]}\n
{plant_params_list[2]}
  {list(takecare_plant.keys())[0]}:{list(takecare_plant.values())[0]}
  {list(takecare_plant.keys())[1]}:{list(takecare_plant.values())[1]}\n
{plant_params_list[3]}
  {list(pot_site.keys())[0]}:{list(pot_site.values())[0]}
  {list(pot_site.keys())[1]}:{list(pot_site.values())[1]}\n
{plant_params_list[4]}
  {list(pot_setting.keys())[0]}:{list(pot_setting.values())[0]}
  {list(pot_setting.keys())[1]}:{list(pot_setting.values())[1]}'''

# 設定提醒項目，並且可以設定時間
watering_dateQuickReplyButton = QuickReplyButton(
    # image_url="https://i.imgur.com/S5ExuB5.png",
    action=DatetimePickerAction(
        label="澆水提醒",
        data="watering_remind",
        mode="datetime"
    )
)
fertilize_dateQuickReplyButton = QuickReplyButton(
    action=DatetimePickerAction(
        label="施肥提醒",
        data="fertilize_remind",
        mode="datetime"
    )
)
clean_dateQuickReplyButton = QuickReplyButton(
    action=DatetimePickerAction(
        label="葉面清潔提醒",
        data="clean_remind",
        mode="datetime"
    )
)
remove_dateQuickReplyButton = QuickReplyButton(
    action=DatetimePickerAction(
        label="移盆提醒",
        data="remove_remind",
        mode="datetime"
    )
)
remind_quickReplyList = QuickReply(
    items = [
        watering_dateQuickReplyButton, fertilize_dateQuickReplyButton,
        clean_dateQuickReplyButton, remove_dateQuickReplyButton
    ]
)
# 提醒時間紀錄
remind_datetime_dict = {
    "澆水提醒時間":"",
    "施肥提醒時間":"",
    "葉面清潔提醒時間":"",
    "移盆提醒時間":""
}
Show_remind_datetime = f'''
{list(remind_datetime_dict.keys())[0]}:{list(remind_datetime_dict.values())[0]}
{list(remind_datetime_dict.keys())[1]}:{list(remind_datetime_dict.values())[1]}
{list(remind_datetime_dict.keys())[2]}:{list(remind_datetime_dict.values())[2]}
{list(remind_datetime_dict.keys())[3]}:{list(remind_datetime_dict.values())[3]}'''

# 提醒推播
def push_watering(user_id):
    line_bot_api.push_message(user_id, TextSendMessage(text='要澆水囉'))
def push_fertilize(user_id):
    line_bot_api.push_message(user_id, TextSendMessage(text='要施肥囉'))
def push_clean(user_id):
    line_bot_api.push_message(user_id, TextSendMessage(text='要清潔葉面囉'))
def push_remove(user_id):
    line_bot_api.push_message(user_id, TextSendMessage(text='要移盆囉'))
# 自動排程器
scheduler = BackgroundScheduler(daemon=True)


# 當收到文字訊息的反應
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    global pic_mode
    global Show_plant_profile
    if event.message.text == "我要紀錄":
        # 更改圖片處理模式：紀錄模式
        pic_mode = "record"
    if event.message.text == "我要診斷":
        # 更改圖片處理模式：診斷模式
        pic_mode = "diagnosis"
    if event.message.text == "查看近期紀錄":
        try:
            reply_img_path = glob(r"/material/*.jpg")

            with open(reply_img_path, 'rb') as fd:
                for chunk in reply_img_path:
                    fd.read(chunk)
                    line_bot_api.reply_message(
                        event.reply_token,
                        ImageSendMessage(
                            originalContentUrl=f"ngrok_url/{chunk}",
                            previewImageUrl=f"ngrok_url/{chunk}")
                    )
        except:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="無歷史紀錄")
            )
    # 設定"植物高度"
    if event.message.text == "植物高度":
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="請選擇植物高度", quick_reply=plant_hight_ReplyList)
        )
    # 點選"植物高度"的按鈕，顯示所有參數
    if event.message.text in plant_hight_List:
        plant_profile['植物高度'] = event.message.text
        Show_plant_profile = f'''{plant_params_list[0]}
  {list(plant_profile.keys())[0]}:{list(plant_profile.values())[0]}
  {list(plant_profile.keys())[1]}:{list(plant_profile.values())[1]}\n
{plant_params_list[1]}
  {list(plant_env.keys())[0]}:{list(plant_env.values())[0]}
  {list(plant_env.keys())[1]}:{list(plant_env.values())[1]}\n
{plant_params_list[2]}
  {list(takecare_plant.keys())[0]}:{list(takecare_plant.values())[0]}
  {list(takecare_plant.keys())[1]}:{list(takecare_plant.values())[1]}\n
{plant_params_list[3]}
  {list(pot_site.keys())[0]}:{list(pot_site.values())[0]}
  {list(pot_site.keys())[1]}:{list(pot_site.values())[1]}\n
{plant_params_list[4]}
  {list(pot_setting.keys())[0]}:{list(pot_setting.values())[0]}
  {list(pot_setting.keys())[1]}:{list(pot_setting.values())[1]}'''
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=Show_plant_profile)
        )
    # 設定"植物年齡"
    if event.message.text == "植物年齡":
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="請選擇植物年齡", quick_reply=plant_age_ReplyList)
        )
    # 點選"植物年齡"的按鈕，顯示所有參數
    if event.message.text in plant_age_List:
        plant_profile['植物年齡'] = event.message.text
        Show_plant_profile = f'''{plant_params_list[0]}
  {list(plant_profile.keys())[0]}:{list(plant_profile.values())[0]}
  {list(plant_profile.keys())[1]}:{list(plant_profile.values())[1]}\n
{plant_params_list[1]}
  {list(plant_env.keys())[0]}:{list(plant_env.values())[0]}
  {list(plant_env.keys())[1]}:{list(plant_env.values())[1]}\n
{plant_params_list[2]}
  {list(takecare_plant.keys())[0]}:{list(takecare_plant.values())[0]}
  {list(takecare_plant.keys())[1]}:{list(takecare_plant.values())[1]}\n
{plant_params_list[3]}
  {list(pot_site.keys())[0]}:{list(pot_site.values())[0]}
  {list(pot_site.keys())[1]}:{list(pot_site.values())[1]}\n
{plant_params_list[4]}
  {list(pot_setting.keys())[0]}:{list(pot_setting.values())[0]}
  {list(pot_setting.keys())[1]}:{list(pot_setting.values())[1]}'''
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=Show_plant_profile)
        )
    # 設定"環境溫度"
    if event.message.text == "設定環境溫度":
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="請選擇環境溫度", quick_reply=plant_env_temp_ReplyList)
        )
    # 點選"環境溫度"的按鈕，顯示所有參數
    if event.message.text in plant_env_temp_List:
        plant_env["環境溫度"] = event.message.text
        Show_plant_profile = f'''{plant_params_list[0]}
  {list(plant_profile.keys())[0]}:{list(plant_profile.values())[0]}
  {list(plant_profile.keys())[1]}:{list(plant_profile.values())[1]}\n
{plant_params_list[1]}
  {list(plant_env.keys())[0]}:{list(plant_env.values())[0]}
  {list(plant_env.keys())[1]}:{list(plant_env.values())[1]}\n
{plant_params_list[2]}
  {list(takecare_plant.keys())[0]}:{list(takecare_plant.values())[0]}
  {list(takecare_plant.keys())[1]}:{list(takecare_plant.values())[1]}\n
{plant_params_list[3]}
  {list(pot_site.keys())[0]}:{list(pot_site.values())[0]}
  {list(pot_site.keys())[1]}:{list(pot_site.values())[1]}\n
{plant_params_list[4]}
  {list(pot_setting.keys())[0]}:{list(pot_setting.values())[0]}
  {list(pot_setting.keys())[1]}:{list(pot_setting.values())[1]}'''
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=Show_plant_profile)
        )
    # 設定"環境通風程度"
    if event.message.text == "設定環境通風程度":
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="請選擇環境通風程度", quick_reply=plant_env_wind_ReplyList)
        )
    # 點選"環境通風程度"的按鈕，顯示所有參數
    if event.message.text in plant_env_wind_List:
        plant_env['環境通風程度'] = event.message.text
        Show_plant_profile = f'''{plant_params_list[0]}
  {list(plant_profile.keys())[0]}:{list(plant_profile.values())[0]}
  {list(plant_profile.keys())[1]}:{list(plant_profile.values())[1]}\n
{plant_params_list[1]}
  {list(plant_env.keys())[0]}:{list(plant_env.values())[0]}
  {list(plant_env.keys())[1]}:{list(plant_env.values())[1]}\n
{plant_params_list[2]}
  {list(takecare_plant.keys())[0]}:{list(takecare_plant.values())[0]}
  {list(takecare_plant.keys())[1]}:{list(takecare_plant.values())[1]}\n
{plant_params_list[3]}
  {list(pot_site.keys())[0]}:{list(pot_site.values())[0]}
  {list(pot_site.keys())[1]}:{list(pot_site.values())[1]}\n
{plant_params_list[4]}
  {list(pot_setting.keys())[0]}:{list(pot_setting.values())[0]}
  {list(pot_setting.keys())[1]}:{list(pot_setting.values())[1]}'''
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=Show_plant_profile)
        )
    # 設定"澆水頻率"
    if event.message.text == "設定澆水頻率":
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="請選擇澆水頻率", quick_reply=watering_freq_ReplyList)
        )
    # 點選"澆水頻率"的按鈕，顯示所有參數
    if event.message.text in watering_freq_List:
        takecare_plant["澆水頻率"] = event.message.text
        Show_plant_profile = f'''{plant_params_list[0]}
  {list(plant_profile.keys())[0]}:{list(plant_profile.values())[0]}
  {list(plant_profile.keys())[1]}:{list(plant_profile.values())[1]}\n
{plant_params_list[1]}
  {list(plant_env.keys())[0]}:{list(plant_env.values())[0]}
  {list(plant_env.keys())[1]}:{list(plant_env.values())[1]}\n
{plant_params_list[2]}
  {list(takecare_plant.keys())[0]}:{list(takecare_plant.values())[0]}
  {list(takecare_plant.keys())[1]}:{list(takecare_plant.values())[1]}\n
{plant_params_list[3]}
  {list(pot_site.keys())[0]}:{list(pot_site.values())[0]}
  {list(pot_site.keys())[1]}:{list(pot_site.values())[1]}\n
{plant_params_list[4]}
  {list(pot_setting.keys())[0]}:{list(pot_setting.values())[0]}
  {list(pot_setting.keys())[1]}:{list(pot_setting.values())[1]}'''
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=Show_plant_profile)
        )
    # 設定"施肥頻率"
    if event.message.text == "設定施肥頻率":
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="請選擇施肥頻率", quick_reply=fertilize_freq_ReplyList)
        )
    # 點選"施肥頻率"的按鈕，顯示所有參數
    if event.message.text in fertilize_freq_List:
        takecare_plant['施肥頻率'] = event.message.text
        Show_plant_profile = f'''{plant_params_list[0]}
  {list(plant_profile.keys())[0]}:{list(plant_profile.values())[0]}
  {list(plant_profile.keys())[1]}:{list(plant_profile.values())[1]}\n
{plant_params_list[1]}
  {list(plant_env.keys())[0]}:{list(plant_env.values())[0]}
  {list(plant_env.keys())[1]}:{list(plant_env.values())[1]}\n
{plant_params_list[2]}
  {list(takecare_plant.keys())[0]}:{list(takecare_plant.values())[0]}
  {list(takecare_plant.keys())[1]}:{list(takecare_plant.values())[1]}\n
{plant_params_list[3]}
  {list(pot_site.keys())[0]}:{list(pot_site.values())[0]}
  {list(pot_site.keys())[1]}:{list(pot_site.values())[1]}\n
{plant_params_list[4]}
  {list(pot_setting.keys())[0]}:{list(pot_setting.values())[0]}
  {list(pot_setting.keys())[1]}:{list(pot_setting.values())[1]}'''
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=Show_plant_profile)
        )
    # 設定"種植空間"
    if event.message.text == "設定種植空間":
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="請選擇種植空間", quick_reply=plantspace_ReplyList)
        )
    # 點選"種植空間"的按鈕，顯示所有參數
    if event.message.text in plantspace_List:
        pot_site["種植空間"] = event.message.text
        Show_plant_profile = f'''{plant_params_list[0]}
  {list(plant_profile.keys())[0]}:{list(plant_profile.values())[0]}
  {list(plant_profile.keys())[1]}:{list(plant_profile.values())[1]}\n
{plant_params_list[1]}
  {list(plant_env.keys())[0]}:{list(plant_env.values())[0]}
  {list(plant_env.keys())[1]}:{list(plant_env.values())[1]}\n
{plant_params_list[2]}
  {list(takecare_plant.keys())[0]}:{list(takecare_plant.values())[0]}
  {list(takecare_plant.keys())[1]}:{list(takecare_plant.values())[1]}\n
{plant_params_list[3]}
  {list(pot_site.keys())[0]}:{list(pot_site.values())[0]}
  {list(pot_site.keys())[1]}:{list(pot_site.values())[1]}\n
{plant_params_list[4]}
  {list(pot_setting.keys())[0]}:{list(pot_setting.values())[0]}
  {list(pot_setting.keys())[1]}:{list(pot_setting.values())[1]}'''
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=Show_plant_profile)
        )
    # 設定"環境光線"
    if event.message.text == "設定環境光線":
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="請選擇環境光線", quick_reply=light_ReplyList)
        )
    # 點選"環境光線"的按鈕，顯示所有參數
    if event.message.text in light_List:
        pot_site['環境光線'] = event.message.text
        Show_plant_profile = f'''{plant_params_list[0]}
  {list(plant_profile.keys())[0]}:{list(plant_profile.values())[0]}
  {list(plant_profile.keys())[1]}:{list(plant_profile.values())[1]}\n
{plant_params_list[1]}
  {list(plant_env.keys())[0]}:{list(plant_env.values())[0]}
  {list(plant_env.keys())[1]}:{list(plant_env.values())[1]}\n
{plant_params_list[2]}
  {list(takecare_plant.keys())[0]}:{list(takecare_plant.values())[0]}
  {list(takecare_plant.keys())[1]}:{list(takecare_plant.values())[1]}\n
{plant_params_list[3]}
  {list(pot_site.keys())[0]}:{list(pot_site.values())[0]}
  {list(pot_site.keys())[1]}:{list(pot_site.values())[1]}\n
{plant_params_list[4]}
  {list(pot_setting.keys())[0]}:{list(pot_setting.values())[0]}
  {list(pot_setting.keys())[1]}:{list(pot_setting.values())[1]}'''
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=Show_plant_profile)
        )
    # 設定"盆器材質"
    if event.message.text == "設定盆器材質":
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="請選擇盆器材質", quick_reply=pot_material_ReplyList)
        )
    # 點選"盆器材質"的按鈕，顯示所有參數
    if event.message.text in pot_material_List:
        pot_setting["盆器材質"] = event.message.text
        Show_plant_profile = f'''{plant_params_list[0]}
  {list(plant_profile.keys())[0]}:{list(plant_profile.values())[0]}
  {list(plant_profile.keys())[1]}:{list(plant_profile.values())[1]}\n
{plant_params_list[1]}
  {list(plant_env.keys())[0]}:{list(plant_env.values())[0]}
  {list(plant_env.keys())[1]}:{list(plant_env.values())[1]}\n
{plant_params_list[2]}
  {list(takecare_plant.keys())[0]}:{list(takecare_plant.values())[0]}
  {list(takecare_plant.keys())[1]}:{list(takecare_plant.values())[1]}\n
{plant_params_list[3]}
  {list(pot_site.keys())[0]}:{list(pot_site.values())[0]}
  {list(pot_site.keys())[1]}:{list(pot_site.values())[1]}\n
{plant_params_list[4]}
  {list(pot_setting.keys())[0]}:{list(pot_setting.values())[0]}
  {list(pot_setting.keys())[1]}:{list(pot_setting.values())[1]}'''
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=Show_plant_profile)
        )
    # 設定"排水孔"
    if event.message.text == "有無排水孔":
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="請選擇是否有排水孔", quick_reply=drainagehole_ReplyList)
        )
    # 點選"排水孔"的按鈕，顯示所有參數
    if event.message.text in drainagehole_List:
        pot_setting['排水孔'] = event.message.text
        Show_plant_profile = f'''{plant_params_list[0]}
  {list(plant_profile.keys())[0]}:{list(plant_profile.values())[0]}
  {list(plant_profile.keys())[1]}:{list(plant_profile.values())[1]}\n
{plant_params_list[1]}
  {list(plant_env.keys())[0]}:{list(plant_env.values())[0]}
  {list(plant_env.keys())[1]}:{list(plant_env.values())[1]}\n
{plant_params_list[2]}
  {list(takecare_plant.keys())[0]}:{list(takecare_plant.values())[0]}
  {list(takecare_plant.keys())[1]}:{list(takecare_plant.values())[1]}\n
{plant_params_list[3]}
  {list(pot_site.keys())[0]}:{list(pot_site.values())[0]}
  {list(pot_site.keys())[1]}:{list(pot_site.values())[1]}\n
{plant_params_list[4]}
  {list(pot_setting.keys())[0]}:{list(pot_setting.values())[0]}
  {list(pot_setting.keys())[1]}:{list(pot_setting.values())[1]}'''
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=Show_plant_profile)
        )
    # 點選"查看植栽設定"的按鈕，顯示所有參數
    if event.message.text == "查看我設定的植栽":
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=Show_plant_profile)
        )
        # 點選"設定提醒時間"的按鈕，選擇提醒按鈕
    if (event.message.text == "設定提醒時間"):
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="請選擇提醒項目", quick_reply=remind_quickReplyList),
        )
    # 點選"查看提醒"的按鈕，查看歷史提醒
    if (event.message.text == "查看提醒"):
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=Show_remind_datetime),
        )

# 當收到圖片訊息的反應
@handler.add(MessageEvent, message=ImageMessage)
def handle_message(event):
    # 取得該用戶上傳的圖片內容
    message_id = event.message.id
    message_content = line_bot_api.get_message_content(message_id)
    temp_file_path=f"""{event.message.id}.jpg"""

    if pic_mode=="record":
        # 上傳圖片到本地端
        # local_save = './material/' + event.message.id + '.jpg'
        with open(temp_file_path, 'wb') as fd:
            b = b''
            for chunk in message_content.iter_content():
                b += chunk
                fd.write(chunk)
            # 上傳圖片到雲端
            # storage_client = storage.Client()
            # bucket_name = "YOUR-BUCKET-NAME"
            # destination_blob_name = f'{event.source.user_id}/image/{event.message.id}.png'
            # bucket = storage_client.bucket(bucket_name)
            # blob = bucket.blob(destination_blob_name)
            # blob.upload_from_filename(temp_file_path)
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="已紀錄照片"))
    if pic_mode=="diagnosis":
        b = b''
        for chunk in message_content.iter_content():
            b += chunk
        img = Image.open(io.BytesIO(b))
        r = classify(img)
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=r))

# 當收到Postback data的反應
@handler.add(PostbackEvent)
def handle_post_message(event):
    global Show_remind_datetime
    user_profile = line_bot_api.get_profile(event.source.user_id)
    user_id = vars(user_profile)["user_id"]
    # 點選 "澆水提醒"，設定時間
    if (event.postback.data.find('watering_remind')== 0):
        remind_datetime = event.postback.params["datetime"].split("T")
        remind_datetime_dict["澆水提醒時間"] = remind_datetime[0] + " " + remind_datetime[1]
        Show_remind_datetime = f'''{list(remind_datetime_dict.keys())[0]}:{list(remind_datetime_dict.values())[0]}
{list(remind_datetime_dict.keys())[1]}:{list(remind_datetime_dict.values())[1]}
{list(remind_datetime_dict.keys())[2]}:{list(remind_datetime_dict.values())[2]}
{list(remind_datetime_dict.keys())[3]}:{list(remind_datetime_dict.values())[3]}'''
        line_bot_api.reply_message(
        event.reply_token,
            TextSendMessage(
                text='已為您設定{} {}澆水提醒'.format(remind_datetime[0], remind_datetime[1])
            )
        )
        if (event.postback.params["datetime"] != 0):
            remind_date = remind_datetime[0].split("-")
            remind_date = [int(i) for i in remind_date]
            remind_time = remind_datetime[1].split(":")
            remind_time = [int(i) for i in remind_time]
            alarm_datetime = datetime(remind_date[0], remind_date[1], remind_date[2], remind_time[0], remind_time[1])
            alarm_datetime = taiwan_tz.localize(alarm_datetime)
            try:
                scheduler.add_job(push_watering, 'date', run_date = alarm_datetime, args = [user_id])
                scheduler.start()
            except:
                pass
    # 點選 "施肥提醒"，設定時間
    if (event.postback.data.find('fertilize_remind')== 0):
        remind_datetime = event.postback.params["datetime"].split("T")
        remind_datetime_dict["施肥提醒時間"] = remind_datetime[0] + " " + remind_datetime[1]
        Show_remind_datetime = f'''{list(remind_datetime_dict.keys())[0]}:{list(remind_datetime_dict.values())[0]}
{list(remind_datetime_dict.keys())[1]}:{list(remind_datetime_dict.values())[1]}
{list(remind_datetime_dict.keys())[2]}:{list(remind_datetime_dict.values())[2]}
{list(remind_datetime_dict.keys())[3]}:{list(remind_datetime_dict.values())[3]}'''
        line_bot_api.reply_message(
        event.reply_token,
            TextSendMessage(
                text='已為您設定{} {}施肥提醒'.format(remind_datetime[0], remind_datetime[1])
            )
        )
        if (event.postback.params["datetime"] != 0):
            remind_date = remind_datetime[0].split("-")
            remind_date = [int(i) for i in remind_date]
            remind_time = remind_datetime[1].split(":")
            remind_time = [int(i) for i in remind_time]
            alarm_datetime = datetime(remind_date[0], remind_date[1], remind_date[2], remind_time[0], remind_time[1])
            alarm_datetime = taiwan_tz.localize(alarm_datetime)
            try:
                scheduler.add_job(push_fertilize, 'date', run_date = alarm_datetime, args = [user_id])
                scheduler.start()
            except:
                pass
    # 點選 "葉面清潔提醒"，設定時間
    if (event.postback.data.find('clean_remind')== 0):
        remind_datetime = event.postback.params["datetime"].split("T")
        remind_datetime_dict["葉面清潔提醒時間"] = remind_datetime[0] + " " + remind_datetime[1]
        Show_remind_datetime = f'''{list(remind_datetime_dict.keys())[0]}:{list(remind_datetime_dict.values())[0]}
{list(remind_datetime_dict.keys())[1]}:{list(remind_datetime_dict.values())[1]}
{list(remind_datetime_dict.keys())[2]}:{list(remind_datetime_dict.values())[2]}
{list(remind_datetime_dict.keys())[3]}:{list(remind_datetime_dict.values())[3]}'''
        line_bot_api.reply_message(
        event.reply_token,
            TextSendMessage(
                text='已為您設定{} {}葉面清潔提醒'.format(remind_datetime[0], remind_datetime[1])
            )
        )
        if (event.postback.params["datetime"] != 0):
            remind_date = remind_datetime[0].split("-")
            remind_date = [int(i) for i in remind_date]
            remind_time = remind_datetime[1].split(":")
            remind_time = [int(i) for i in remind_time]
            alarm_datetime = datetime(remind_date[0], remind_date[1], remind_date[2], remind_time[0], remind_time[1])
            alarm_datetime = taiwan_tz.localize(alarm_datetime)
            try:
                scheduler.add_job(push_clean, 'date', run_date = alarm_datetime, args = [user_id])
                scheduler.start()
            except:
                pass
    # 點選 "移盆提醒"，設定時間
    if (event.postback.data.find('remove_remind')== 0):
        remind_datetime = event.postback.params["datetime"].split("T")
        remind_datetime_dict["移盆提醒時間"] = remind_datetime[0] + " " + remind_datetime[1]
        Show_remind_datetime = f'''{list(remind_datetime_dict.keys())[0]}:{list(remind_datetime_dict.values())[0]}
{list(remind_datetime_dict.keys())[1]}:{list(remind_datetime_dict.values())[1]}
{list(remind_datetime_dict.keys())[2]}:{list(remind_datetime_dict.values())[2]}
{list(remind_datetime_dict.keys())[3]}:{list(remind_datetime_dict.values())[3]}'''
        line_bot_api.reply_message(
        event.reply_token,
            TextSendMessage(
                text='已為您設定{} {}移盆提醒'.format(remind_datetime[0], remind_datetime[1])
            )
        )
        if (event.postback.params["datetime"] != 0):
            remind_date = remind_datetime[0].split("-")
            remind_date = [int(i) for i in remind_date]
            remind_time = remind_datetime[1].split(":")
            remind_time = [int(i) for i in remind_time]
            alarm_datetime = datetime(remind_date[0], remind_date[1], remind_date[2], remind_time[0], remind_time[1])
            alarm_datetime = taiwan_tz.localize(alarm_datetime)
            try:
                scheduler.add_job(push_remove, 'date', run_date = alarm_datetime, args = [user_id])
                scheduler.start()
            except:
                pass

# 執行line主程式
if __name__ == "__main__":
    app.run()
