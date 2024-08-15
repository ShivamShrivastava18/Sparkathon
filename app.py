from flask import Flask, request, jsonify, render_template, Response
import json
import requests
from bs4 import BeautifulSoup
import PIL.Image
import time
import google.generativeai as genai
import uuid

genai.configure(api_key='AIzaSyBEA78n_neLXQAeqd8Pdmuce7NOU2s7ARg')

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process_image', methods=['POST'])
def process_image():
    if 'image' not in request.files:
        return jsonify({'error': 'No image provided'}), 400

    image = request.files['image']
    img = PIL.Image.open(image)

    prompt = """This image contains an image of a dish.
    Given the image, based on what you see in the image, making sure to note all the ingredients required to make the dish. 
    Also give ingredients for any subdish that is present in the picture. Return output in json format:
    {ingredients: [ingredients1, ingredients2, ingredients3, etc]}"""

    # Assuming you have a generative AI model configured
    model = genai.GenerativeModel('gemini-1.5-flash')
    response = model.generate_content([prompt, img])
    response_text = response.text

    if response_text.startswith("```json") and response_text.endswith("```"):
        response_text = response_text[7:-3].strip()

    try:
        parsed_response = json.loads(response_text)
        ingredients_list = parsed_response.get('ingredients', [])
    except json.JSONDecodeError as e:
        return jsonify({'error': 'Error decoding JSON', 'details': str(e)}), 500

    # Store ingredients list in a temporary place for streaming
    with open('ingredients.json', 'w') as f:
        json.dump({'ingredients': ingredients_list}, f)

    return jsonify({'status': 'Processing complete'}), 200

@app.route('/stream_updates')
def stream_updates():
    def generate():
        try:
            with open('ingredients.json', 'r') as f:
                ingredients_data = json.load(f)
                ingredients_list = ingredients_data.get('ingredients', [])

            headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/61.0.3163.100 Safari/537.36'}
            for i in ingredients_list:
                formatted_ingredient = i.replace(" ", "%20")
                search_url = f"https://www.walmart.com/search?q={formatted_ingredient}"
                
                page = requests.get(search_url, headers=headers)
                fd = page.content
                soup = BeautifulSoup(fd, 'html.parser')
                best_seller_product = soup.find('span', text="Best seller")
                if best_seller_product:
                    product_container = best_seller_product.find_parent('div', class_="sans-serif mid-gray relative flex flex-column w-100 hide-child-opacity")
                    if product_container:
                        image_tag = product_container.find('img', {'data-testid': 'productTileImage'})
                        image_url = image_tag['src'] if image_tag else None

                        name_tag = product_container.find('span', {'data-automation-id': 'product-title'})
                        product_name = name_tag.get_text(strip=True) if name_tag else None

                        price_dollars = product_container.find('span', class_='f2')
                        price_cents = product_container.find_all('span', class_='f6 f5-l')

                        product_price = ""
                        if price_dollars:
                            product_price += price_dollars.get_text(strip=True)
                        if price_cents:
                            product_price += "." + price_cents[-1].get_text(strip=True)  # Get the last span for cents

                        unique_code = str(uuid.uuid4())

                        product_data = {
                            'image_url': image_url,
                            'product_name': product_name,
                            'product_price': product_price,
                            'unique_code': unique_code
                        }

                        yield f"data: {json.dumps({'product': product_data})}\n\n"

                time.sleep(20)  # Sleep for a short period to avoid being blocked by the website
            yield f"data: {json.dumps({'final': 'Happy Cooking :D'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(generate(), content_type='text/event-stream')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=4000, debug=True)
