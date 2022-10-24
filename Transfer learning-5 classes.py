import io

import numpy as np
from tensorflow.keras.models import load_model
from PIL import Image, ImageOps
from flask import Flask, request, abort

from linebot import (
    LineBotApi, WebhookHandler
)
from linebot.exceptions import (
    InvalidSignatureError
)
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, ImageMessage
)

model = models.load_model("transfer_best_v2.h5")

all_class = ['MD_Normal', 'MD_old_water', 'MD_sunburnt', 'MD_bac_fungi', 'Others']

app = Flask(__name__)

line_bot_api = LineBotApi('YOUR_CHANNEL_ACCESS_TOKEN')
handler = WebhookHandler('YOUR_CHANNEL_SECRET')

@app.route("/callback", methods=['POST'])
def callback():
    # get X-Line-Signature header value
    signature = request.headers['X-Line-Signature']

    # get request body as text
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    # handle webhook body
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("Invalid signature. Please check your channel access token/channel secret.")
        abort(400)

    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=event.message.text))


@handler.add(MessageEvent, message=ImageMessage)
def handle_message(event):
    message_id = event.message.id
    message_content = line_bot_api.get_message_content(message_id)
        
    b = b''
    for chunk in message_content.iter_content():
        b += chunk
    img = Image.open(io.BytesIO(b))
    r = classify(img)
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=r))


def classify(img):
    img = ImageOps.fit(img, model.input.shape[1:3])
    img = np.expand_dims(img, axis=0)
    img = tf.keras.applications.efficientnet_v2.preprocess_input(img, data_format=None)
    prediction = model.predict(img)
    return all_class[prediction.argmax(axis=-1)]

if __name__ == "__main__":
    app.run()