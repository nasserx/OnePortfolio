from dotenv import load_dotenv
load_dotenv()

from config import Config, DevelopmentConfig
from portfolio_app import create_app

app = create_app(DevelopmentConfig if __name__ == '__main__' else Config)


if __name__ == '__main__':
    app.run(debug=app.debug)
