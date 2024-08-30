import logging
import re
from datetime import datetime, timedelta
import json
import aiohttp
from .const import APTNER_URL, AUTH_URL, CAR_LIST_URL, FEE_URL, RESERVATION_URL, RESERVATION_LIST_URL

_LOGGER = logging.getLogger(__name__)

class Aptner:
    headers = {'Content-Type': 'application/json'}
    token = None

    def __init__(self, hass, user_id, password):
        self.hass = hass
        self.id = user_id
        self.password = password
        self.session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=False),
            headers=self.headers
        )

    async def auth(self):
        """로그인을 수행합니다."""
        try:
            resp = await self.session.post(
                url=f"{APTNER_URL}{AUTH_URL}",
                data=json.dumps({'id': self.id, 'password': self.password})
            )
            resp.raise_for_status()
            self.token = await resp.json()
            self.headers['Authorization'] = 'Bearer ' + self.token['accessToken']
        except Exception as ex:
            _LOGGER.error("로그인 실패: %s", ex)
            raise ex

    async def get(self, get_request):
        async with self.session.get(APTNER_URL + get_request, headers=self.headers) as response:
            if response.status == 401:
                await self.auth()
                async with self.session.get(APTNER_URL + get_request, headers=self.headers) as new_response:
                    new_response.raise_for_status()
                    return await new_response.json()
            else:
                response.raise_for_status()
                return await response.json()

    async def post(self, post_request, data):
        if isinstance(data, dict):
            data = json.dumps(data)
        async with self.session.post(APTNER_URL + post_request, headers=self.headers, data=data) as response:
            if response.status == 401:
                await self.auth()
                async with self.session.post(APTNER_URL + post_request, headers=self.headers, data=data) as new_response:
                    new_response.raise_for_status()
                    return await new_response.json()
            else:
                response.raise_for_status()
                return await response.json()

    async def find_car(self):
        try:
            monthly_access_history = await self.get(CAR_LIST_URL)
            now = datetime.now()
            for monthly_parking_history in monthly_access_history['monthlyParkingHistoryList']:
                first_history = monthly_parking_history['visitCarUseHistoryReportList'][0]
                in_datetime_str = first_history['inDatetime']
                in_datetime = datetime.strptime(in_datetime_str, '%Y.%m.%d %H:%M')
                time_diff = now - in_datetime
                if time_diff <= timedelta(seconds=50):
                    return first_history['carNo']
            return None
        except Exception as e:
            _LOGGER.error("차량 찾기 실패: %s", e)
            raise e

    async def get_cost(self):
        try:
            cost_detail = await self.get(FEE_URL)
            cost = json.dumps(cost_detail['feeList'], indent=2, ensure_ascii=False)
            cost = json.loads(cost)
            first_item = cost[0]
            formattedFee = "{:,}".format(first_item['currentFee'])
            formatted_str = f"{first_item['year']}년 {first_item['month']}월 {formattedFee}원"
            return formatted_str
        except Exception as e:
            _LOGGER.error("비용 조회 실패: %s", e)
            raise e

    async def reservation_car(self, car_no, days):
        """차량 예약을 수행합니다."""
        # 차량 번호 검증
        if not self.validate_car_no(car_no):
            raise ValueError("차량 번호 형식이 올바르지 않습니다. '12가1234' 또는 '123가1234' 형식이어야 합니다.")

        try:
            cur_date = datetime.today().strftime('%Y.%m.%d')
            reservation_form = {
                'visitDate': cur_date,
                'purpose': '지인/가족방문',
                'carNo': str(car_no).strip(),
                'days': days,
                'phone': '01012345678'
            }
            await self.post(RESERVATION_URL, reservation_form)
        except Exception as e:
            _LOGGER.error("차량 예약 실패: %s", e)
            raise e

    async def get_current_reservation_list(self):
        try:
            reservation_list = await self.get(RESERVATION_LIST_URL)
            json_form = json.dumps(reservation_list, indent=2, ensure_ascii=False)
            json_form = json.loads(json_form)
            reserve_list = json_form['reserveList']
            reserve_formed_list = [f'잔여 시간 : {json_form["visitConfig"]["availableLimitText"]}']
            for reserve in reserve_list:
                reserve_formed_list.append(f"방문 날짜 : {reserve['visitDate']}, 차량 번호 : {reserve['carNo']}")
            return reserve_formed_list
        except Exception as e:
            _LOGGER.error("현재 예약 목록 조회 실패: %s", e)
            raise e

    def validate_car_no(self, car_no):
        """차량 번호 형식을 검증합니다."""
        pattern = re.compile(r"^\d{2,3}[가-힣]\d{4}$")
        return bool(pattern.match(car_no))
