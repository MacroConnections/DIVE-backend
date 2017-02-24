from flask import render_template, current_app, request, make_response
from flask_restful import Resource, reqparse
from flask_login import current_user, login_user, logout_user
from datetime import timedelta, datetime

from dive.server.auth.token import generate_confirmation_token, confirm_token
from dive.server.auth.email import send_email
from dive.base.core import login_manager, db
from dive.base.db import AuthStatus, AuthMessage, row_to_dict
from dive.base.db.accounts import validate_registration, register_user, delete_user, check_user_auth, confirm_user, get_user, check_email_exists
from dive.base.db.models import User
from dive.base.serialization import jsonify

import logging
logger = logging.getLogger(__name__)

COOKIE_DURATION = timedelta(days=365)


# Expired token
# http://localhost:3009/auth/activate/Imt6aEB0ZXN0LmNvbXUi.C5C0EQ.b55oev3lDumYZby8L5ChLINoD80
class Confirm_Token(Resource):
    def get(self, token):
        email = confirm_token(token)
        if not email:
            return jsonify({
                'status': 'failure',
                'message': 'The confirmation link is invalid or expired.'
            }, status=401)

        user = get_user(email=email)
        if user.confirmed:
            response = jsonify({
                'status': 'success',
                'message': 'Account for %s already activated.' % email,
                'alreadyActivated': True,
                'user': row_to_dict(user)
            }, status=200)
            response.set_cookie('confirmed', str(True), expires=datetime.utcnow() + COOKIE_DURATION, domain=current_app.config['COOKIE_DOMAIN'])
            return response
        else:
            confirm_user(email=email)
            login_user(user, remember=True)
            response = jsonify({
                'status': 'success',
                'message': 'Account for %s successfully activated.' % email,
                'alreadyActivated': False,
                'user': row_to_dict(user)
            })
            response.set_cookie('username', user.username, expires=datetime.utcnow() + COOKIE_DURATION, domain=current_app.config['COOKIE_DOMAIN'])
            response.set_cookie('email', user.email, expires=datetime.utcnow() + COOKIE_DURATION, domain=current_app.config['COOKIE_DOMAIN'])
            response.set_cookie('user_id', str(user.id), expires=datetime.utcnow() + COOKIE_DURATION, domain=current_app.config['COOKIE_DOMAIN'])
            response.set_cookie('confirmed', str(True), expires=datetime.utcnow() + COOKIE_DURATION, domain=current_app.config['COOKIE_DOMAIN'])
            return response


resendEmailPostParser = reqparse.RequestParser()
resendEmailPostParser.add_argument('email', type=str, required=True, location='json')
resendEmailPostParser.add_argument('os', type=str, required=True, location='json')
resendEmailPostParser.add_argument('browser', type=str, required=True, location='json')
class Resend_Email(Resource):
    def post(self):
        args = resendEmailPostParser.parse_args()
        email = args.get('email')
        os = args.get('os')
        browser = args.get('browser')

        user = check_email_exists(email)
        if user:
            token = generate_confirmation_token(email)
            site_url = '%s://%s' % (current_app.config['PREFERRED_URL_SCHEME'], current_app.config['SITE_URL'])
            confirm_url = '%s/auth/activate/%s' % (site_url, token)
            html = render_template('confirm_email.html',
                username=user.username,
                confirm_url=confirm_url,
                site_url=site_url,
                support_url='mailto:dive@media.mit.edu',
                os=os,
                browser=browser
            )
            send_email(email, 'Activate Your DIVE Account', html)
            return jsonify({
                'status': 'success',
                'message': 'A confirmation e-mail has been sent to %s' % email
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'No account corresponds to that e-mail address.'
            }, status=401)


resetPasswordPostParser = reqparse.RequestParser()
resetPasswordPostParser.add_argument('email', type=str, required=True, location='json')
resetPasswordPostParser.add_argument('os', type=str, required=True, location='json')
resetPasswordPostParser.add_argument('browser', type=str, required=True, location='json')
class Reset_Password(Resource):
    def post(self):
        args = resetPasswordPostParser.parse_args()
        email = args.get('email')
        os = args.get('os')
        browser = args.get('browser')

        user = check_email_exists(email)
        if user:
            token = generate_confirmation_token(email)
            site_url = '%s://%s' % (current_app.config['PREFERRED_URL_SCHEME'], current_app.config['SITE_URL'])
            confirm_url = '%s/auth/reset_password/%s' % (site_url, token)
            html = render_template('reset_password.html',
                username=user.username,
                confirm_url=confirm_url,
                site_url=site_url,
                support_url='mailto:dive@media.mit.edu',
                os=os,
                browser=browser
            )
            send_email(email, 'Reset Your DIVE Password', html)
            return jsonify({
                'status': 'success',
                'message': 'A password reset link has been sent to %s' % email
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'No account corresponds to that e-mail address.'
            }, status=401)


registerPostParser = reqparse.RequestParser()
registerPostParser.add_argument('username', type=str, location='json')
registerPostParser.add_argument('name', type=str, default='', location='json')
registerPostParser.add_argument('email', type=str, location='json')
registerPostParser.add_argument('password', type=str, location='json')
registerPostParser.add_argument('os', type=str, location='json')
registerPostParser.add_argument('browser', type=str, location='json')
registerPostParser.add_argument('remember', type=bool, location='json')
class Register(Resource):
    def post(self):
        args = registerPostParser.parse_args()
        username = args.get('username')
        name = args.get('name')
        email = args.get('email')
        password = args.get('password')
        os = args.get('os')
        browser = args.get('browser')
        remember = args.get('remember', True)

        registration_result, valid_registration = validate_registration(username, email)
        if valid_registration:
            user = register_user(username, email, password, confirmed=False)
            login_user(user, remember=remember)

            site_url = '%s://%s' % (current_app.config['PREFERRED_URL_SCHEME'], current_app.config['SITE_URL'])
            token = generate_confirmation_token(email)
            confirm_url = '%s/auth/activate/%s' % (site_url, token)
            html = render_template('confirm_email.html',
                username=username,
                confirm_url=confirm_url,
                site_url=site_url,
                support_url='mailto:dive@media.mit.edu',
                os=os,
                browser=browser
            )

            send_email('kzh@mit.edu', 'Activate Your DIVE Account', html)

            response = jsonify({
                'status': 'success',
                'message': 'A confirmation e-mail has been sent to %s' % email,
                'user': row_to_dict(user)
            })
            response.set_cookie('username', user.username, expires=datetime.utcnow() + COOKIE_DURATION, domain=current_app.config['COOKIE_DOMAIN'])
            response.set_cookie('email', user.email, expires=datetime.utcnow() + COOKIE_DURATION, domain=current_app.config['COOKIE_DOMAIN'])
            response.set_cookie('user_id', str(user.id), expires=datetime.utcnow() + COOKIE_DURATION, domain=current_app.config['COOKIE_DOMAIN'])
            response.set_cookie('confirmed', str(user.confirmed), expires=datetime.utcnow() + COOKIE_DURATION, domain=current_app.config['COOKIE_DOMAIN'])

            return response

        else:
            return jsonify({
                'status': 'error',
                'message': registration_result
            }, status=401)


userDeleteParser = reqparse.RequestParser()
userDeleteParser.add_argument('user_id', type=str, required=True)
userDeleteParser.add_argument('password', type=str, required=True)
class User(Resource):
    def delete(self):
        args = userDeleteParser.parse_args()
        user_id = args.get('user_id')
        password = args.get('password')

        deleted_user = delete_user(user_id, password)
        return jsonify(deleted_user)


loginPostParser = reqparse.RequestParser()
loginPostParser.add_argument('username', type=str, required=True, location='json')
loginPostParser.add_argument('email', type=str, required=True, location='json')
loginPostParser.add_argument('password', type=str, location='json')
loginPostParser.add_argument('rememberMe', type=bool, default=True, location='json')
class Login(Resource):
    def post(self):
        args = loginPostParser.parse_args()
        username = args.get('username')
        email = args.get('email')
        password = args.get('password')
        rememberMe = args.get('rememberMe')

        user_auth_object = check_user_auth(password, email=email, username=username)
        user = user_auth_object['user']
        status = user_auth_object['status']
        message = user_auth_object['message']
        error_type = user_auth_object['error_type']

        if status == AuthStatus.SUCCESS.value:
            login_user(user, remember=rememberMe)
            if user.username:
                message = 'Welcome back %s!' % user.username
            else:
                message = 'Welcome back!'
            response = jsonify({
                'status': status,
                'message': message,
                'user': row_to_dict(user)
            })

            response.set_cookie('username', user.username, expires=datetime.utcnow() + COOKIE_DURATION, domain=current_app.config['COOKIE_DOMAIN'])
            response.set_cookie('email', user.email, expires=datetime.utcnow() + COOKIE_DURATION, domain=current_app.config['COOKIE_DOMAIN'])
            response.set_cookie('user_id', str(user.id), expires=datetime.utcnow() + COOKIE_DURATION, domain=current_app.config['COOKIE_DOMAIN'])
            response.set_cookie('confirmed', str(user.confirmed), expires=datetime.utcnow() + COOKIE_DURATION, domain=current_app.config['COOKIE_DOMAIN'])

            return response
        else:
            return jsonify({
                'status': status,
                'message': {
                    'login': message,
                },
            }, status=401)


logoutPostParser = reqparse.RequestParser()
logoutPostParser.add_argument('username', type=str, location='json')
class Logout(Resource):
    def post(self):
        logout_user()
        response = jsonify({
            'status': 'success',
            'message': 'You have been logged out.'
        })
        response.set_cookie('username', '', expires=0, domain=current_app.config['COOKIE_DOMAIN'])
        response.set_cookie('email', '', expires=0, domain=current_app.config['COOKIE_DOMAIN'])
        response.set_cookie('user_id', '', expires=0, domain=current_app.config['COOKIE_DOMAIN'])
        response.set_cookie('confirmed', str(False), expires=0, domain=current_app.config['COOKIE_DOMAIN'])

        return response
