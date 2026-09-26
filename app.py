from datetime import datetime, timedelta, timezone
import os

import requests
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

API_KEY = "516b5a714a880938859f18e1bfa47a5a"
API_BASE = "https://api.openweathermap.org/data/2.5"

ICON_MAPPING = {
    "Clear": "☀️",
    "Clouds": "☁️",
    "Rain": "🌧️",
    "Drizzle": "🌦️",
    "Thunderstorm": "⛈️",
    "Snow": "❄️",
    "Mist": "🌫️",
    "Smoke": "🌫️",
    "Haze": "🌫️",
    "Dust": "💨",
    "Fog": "🌫️",
}


def get_weather_icon(description):
    description = description or ""
    for key, emoji in ICON_MAPPING.items():
        if key.lower() in description.lower():
            return emoji
    return "🌤️"


def render_error(message, city="", unit="C", lat="", lon=""):
    return render_template(
        "index.html",
        error=message,
        city=city,
        unit=unit,
        lat=lat,
        lon=lon,
    )


@app.get("/api/weather")
def current_weather_api():
    city = request.args.get("city", "Ranchi").strip() or "Ranchi"
    unit = request.args.get("unit", "C").upper()
    units = "metric" if unit == "C" else "imperial"

    try:
        response = requests.get(
            f"{API_BASE}/weather",
            params={"q": city, "appid": API_KEY, "units": units},
            timeout=10,
        )
        response.raise_for_status()
        current = response.json()
        current_weather = current["weather"][0]
        current_main = current["main"]

        result = jsonify({
            "city": f"{current['name']}, {current['sys']['country']}",
            "temperature": round(current_main["temp"]),
            "description": current_weather["description"].title(),
            "humidity": current_main["humidity"],
            "wind": round(current["wind"]["speed"] * (3.6 if unit == "C" else 1), 1),
            "unit": unit,
        })
        result.headers["Access-Control-Allow-Origin"] = "*"
        return result
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response else 502
        return jsonify({"error": "Weather service request failed."}), status
    except (requests.RequestException, KeyError, TypeError, ValueError):
        return jsonify({"error": "Weather data is unavailable."}), 502


@app.route("/", methods=["GET", "POST"])
def index():
    weather_data = None
    error_msg = None
    selected_city = ""
    selected_unit = "C"
    selected_lat = ""
    selected_lon = ""

    if request.method == "POST":
        lat = request.form.get("lat", "").strip()
        lon = request.form.get("lon", "").strip()
        city = request.form.get("city", "").strip()
        selected_unit = request.form.get("unit", "C").upper()
        selected_city = city

        if selected_unit not in {"C", "F"}:
            selected_unit = "C"

        if not API_KEY:
            return render_error(
                "Set OPENWEATHER_API_KEY before starting the app.",
                selected_city,
                selected_unit,
                lat,
                lon,
            )

        if lat or lon:
            try:
                float(lat)
                float(lon)
            except ValueError:
                return render_error(
                    "Invalid GPS coordinates.",
                    selected_city,
                    selected_unit,
                    lat,
                    lon,
                )

            if not lat or not lon:
                return render_error(
                    "Both latitude and longitude are required.",
                    selected_city,
                    selected_unit,
                    lat,
                    lon,
                )

            location_params = {"lat": lat, "lon": lon}
            selected_lat, selected_lon = lat, lon
        elif city:
            location_params = {"q": city}
        else:
            return render_error(
                "Enter a city or use your current location.",
                selected_city,
                selected_unit,
            )

        units = "metric" if selected_unit == "C" else "imperial"
        common_params = {
            **location_params,
            "appid": API_KEY,
            "units": units,
        }

        try:
            current_response = requests.get(
                f"{API_BASE}/weather",
                params=common_params,
                timeout=10,
            )
            forecast_response = requests.get(
                f"{API_BASE}/forecast",
                params=common_params,
                timeout=10,
            )

            current_response.raise_for_status()
            forecast_response.raise_for_status()

            current = current_response.json()
            forecast = forecast_response.json()
            forecast_items = forecast.get("list", [])

            if not forecast_items:
                return render_error(
                    "No forecast data was returned.",
                    selected_city,
                    selected_unit,
                    selected_lat,
                    selected_lon,
                )

            timezone_offset = current.get("timezone", 0)
            local_now = datetime.now(timezone.utc) + timedelta(
                seconds=timezone_offset
            )
            today = local_now.date()
            tomorrow = today + timedelta(days=1)

            today_temps = []
            tomorrow_temps = []
            today_conditions = set()
            tomorrow_conditions = set()
            chart_labels = []
            chart_temps = []

            for item in forecast_items:
                local_time = datetime.fromtimestamp(
                    item["dt"], timezone.utc
                ) + timedelta(seconds=timezone_offset)

                item_date = local_time.date()
                temp = item["main"]["temp"]
                condition = item["weather"][0]["main"]

                if item_date == today:
                    today_temps.append(temp)
                    today_conditions.add(condition)
                elif item_date == tomorrow:
                    tomorrow_temps.append(temp)
                    tomorrow_conditions.add(condition)

                if len(chart_labels) < 8:
                    chart_labels.append(local_time.strftime("%H:%M"))
                    chart_temps.append(round(temp, 1))

            current_weather = current["weather"][0]
            current_main = current["main"]
            raw_visibility = current.get("visibility", 0)

            visibility = (
                f"{round(raw_visibility / 1000, 1)} km"
                if selected_unit == "C"
                else f"{round(raw_visibility / 1609.344, 1)} mi"
            )

            def forecast_summary(temps, conditions):
                return {
                    "min": round(min(temps)) if temps else "--",
                    "max": round(max(temps)) if temps else "--",
                    "icon": get_weather_icon(
                        sorted(conditions)[0] if conditions else "Clear"
                    ),
                    "cond": "/".join(sorted(conditions)) or "Clear",
                }

            weather_data = {
                "city": f"{current['name']}, {current['sys']['country']}",
                "live_temp": round(current_main["temp"]),
                "live_feels": round(current_main["feels_like"]),
                "live_humidity": current_main["humidity"],
                "live_pressure": current_main["pressure"],
                "live_visibility": visibility,
                "live_wind": round(current["wind"]["speed"], 1),
                "live_desc": current_weather["description"].title(),
                "live_icon": get_weather_icon(current_weather["main"]),
                "chart_labels": chart_labels,
                "chart_temps": chart_temps,
                "today": forecast_summary(today_temps, today_conditions),
                "tomorrow": forecast_summary(
                    tomorrow_temps, tomorrow_conditions
                ),
            }

            selected_city = current["name"]

        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response else 0
            if status == 401:
                error_msg = "Invalid OpenWeatherMap API key."
            elif status == 404:
                error_msg = "City not found."
            else:
                error_msg = "Weather service request failed."
        except requests.RequestException:
            error_msg = "Network connection failed."
        except (KeyError, TypeError, ValueError):
            error_msg = "Invalid weather data received."

    return render_template(
        "index.html",
        weather=weather_data,
        error=error_msg,
        city=selected_city,
        unit=selected_unit,
        lat=selected_lat,
        lon=selected_lon,
    )


if __name__ == "__main__":
    app.run(debug=True)