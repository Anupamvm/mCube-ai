from __future__ import absolute_import

import jwt
from neo_api_client.exceptions import ApiValueError
from neo_api_client.urls import BASE_URL
from neo_api_client.settings import PROD_URL


class NeoUtility:
    """
    Configuration holder for the Neo API client (v2 API).

    Stores session tokens, base URL, and data center info
    obtained from the TOTP login + MPIN validate flow.
    """

    def __init__(
            self,
            host=None,
            access_token=None,
            neo_fin_key=None,
            consumer_key=None
    ):
        self.host = host
        self.view_token = None
        self.sid = None
        self.userId = None
        self.edit_token = None
        self.edit_sid = None
        self.edit_rid = None
        self.serverId = None
        self.login_params = None
        self.neo_fin_key = neo_fin_key
        self.data_center = None
        self.base_url = None
        self.totp_session_id = None
        self.consumer_key = consumer_key

    def extract_userid(self, view_token):
        if not view_token:
            raise ApiValueError(
                "View Token hasn't been Generated Kindly Call the Login Function and Try to Generate OTP")
        decode_jwt = jwt.decode(view_token, options={"verify_signature": False})
        userid = decode_jwt.get("sub")
        self.userId = userid
        return userid

    def get_domain(self, is_login=False):
        """
        Return the appropriate base URL.

        - is_login=True: Return the fixed login base URL (mis.kotaksecurities.com)
        - is_login=False: Return the dynamic base_url from login response
        """
        if is_login:
            return BASE_URL
        else:
            return self.base_url

    def get_url_details(self, api_info):
        domain_info = self.get_domain()
        url_path = PROD_URL.get(api_info)
        if not url_path:
            raise ApiValueError(f"Unknown API endpoint: {api_info}")
        domain_info += '/' + url_path
        return domain_info

    def get_neo_fin_key(self):
        if self.neo_fin_key:
            return self.neo_fin_key
        return "neotradeapi"
