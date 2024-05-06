class Seminar:
    def __init__(self, name, url, actual_price=None, new_price=None, discount=False):
        self.name = name
        self.url = url
        self.actual_price = actual_price
        self.new_price = new_price
        self.discount = discount
