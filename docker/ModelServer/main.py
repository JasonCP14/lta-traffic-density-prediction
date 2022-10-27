import base64
from fastapi import Body, FastAPI, File
from segmentation import get_count_model, get_congestion_model, get_image_from_bytes
from starlette.responses import Response
import io
from PIL import Image
import json
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import requests

count_model = get_count_model()
congestion_model = get_congestion_model()

app = FastAPI(
    title = "ModelServer",
    description = "Runs the model and get predictions",
    version = "0.0.1",
)

origins = [
    "http://localhost",
    "http://localhost:8000",
    "*"
]

app.add_middleware(
     CORSMiddleware,
     allow_origins=origins,
     allow_credentials=True,
     allow_methods=["*"],
     allow_headers=["*"],
)

@app.post("/object-to-json")
async def detect_food_return_json_result(file: bytes = File(...)):
    input_image = get_image_from_bytes(file)
    results = count_model(input_image)
    detect_res = results.pandas().xyxy[0].to_json(orient="records")
    detect_res = json.loads(detect_res)
    return {"result": detect_res}

@app.post("/object-to-img")
async def detect_food_return_base64_img(file: bytes = File(...)):
    input_image = get_image_from_bytes(file)
    results = count_model(input_image)
    results.render()  # updates results.ims with boxes and labels
    for img in results.ims:
        bytes_io = io.BytesIO()
        img_base64 = Image.fromarray(img)
        img_base64.save(bytes_io, format="jpeg")
    return Response(content=bytes_io.getvalue(), media_type="image/jpeg")

@app.post("/get_prediction")
async def get_prediction(file: bytes = File(...)):
    input_image = get_image_from_bytes(file)
    count_result = count_model(input_image)
    count_result.render()

    congestion_result = congestion_model(input_image)
    congestion_result.render()

    bytes_io = io.BytesIO()
    img_base64 = Image.fromarray(count_result.ims[0])
    img_base64.save(bytes_io, format = "jpeg")
    img_string = base64.b64encode(bytes_io.getvalue())
    count_img_strings = [img_string]

    bytes_io = io.BytesIO()
    img_base64 = Image.fromarray(congestion_result.ims[0])
    img_base64.save(bytes_io, format = "jpeg")
    img_string = base64.b64encode(bytes_io.getvalue())
    congestion_img_strings = [img_string]

    # Image.open(io.BytesIO(base64.b64decode(img_string))) # to build Image
    # return Response(content = io.BytesIO(base64.b64decode(img_string)).getvalue(), media_type = "image/jpeg")

    output_payload = {"count_img_strings": count_img_strings, "congestion_img_strings": congestion_img_strings}
    requests.post("http://fileservice:4321", output_payload)
    return output_payload

@app.post("/get_predictions")
async def get_predictions(input_payload: dict = Body(...)):
    image_links = list(map(lambda x: x["ImageLink"], input_payload["value"]))
    input_images = []
    camera_ids = []
    images_datetime = []
    for image_link in image_links:
        camera_id = image_link.split("/")[5].split("?")[0].split("_")[0]
        image_datetime = image_link.split("/")[5].split("?")[0].split("_")[2]
        image_datetime = datetime.strptime(image_datetime, '%Y%m%d%H%M%S')
        image_datetime = image_datetime.strftime('%Y/%m/%d %H.%M.%S')

        try:
            response = requests.get(image_link)
            img = Image.open(io.BytesIO(response.content))
            input_images.append(img)
            camera_ids.append(camera_id)
            images_datetime.append(image_datetime)
        except Exception as e:
            print(str(e))

    if input_images:
        count_results = count_model(input_images)
        count_results.render()

        congestion_results = congestion_model(input_images)
        congestion_results.render()

        count_vehicles = list(map(len, count_results.pandas().xyxy))
        congestions = list(map(lambda x: min(sum(x["name"] == "congested"), 1), congestion_results.pandas().xyxy))

        count_img_strings = []
        for img in count_results.ims:
            bytes_io = io.BytesIO()
            img_base64 = Image.fromarray(img)
            img_base64.save(bytes_io, format = "jpeg")
            img_string = base64.b64encode(bytes_io.getvalue())
            count_img_strings.append(img_string)

        congestion_img_strings = []
        for img in congestion_results.ims:
            bytes_io = io.BytesIO()
            img_base64 = Image.fromarray(img)
            img_base64.save(bytes_io, format = "jpeg")
            img_string = base64.b64encode(bytes_io.getvalue())
            congestion_img_strings.append(img_string)

        output_payload = {"camera_id": camera_ids, "images_datetime": images_datetime, "count": count_vehicles, "congestion": congestions,
                "count_img_strings": count_img_strings, "congestion_img_strings": congestion_img_strings}
        
        requests.post("http://fileservice:4321", output_payload)
        return output_payload #uvicorn main:app --reload --host 0.0.0.0 --port 8000

@app.get('/notify/v1/health')
def get_health():
    return dict(msg='OK')