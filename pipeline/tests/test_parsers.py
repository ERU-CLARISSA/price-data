import unittest

from price import estat, maff_otoku, maff_outlook, seasonal, wareki


class Wareki(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(str(wareki.parse("令和８年11月２日の週")), "2026-11-02")
        self.assertEqual(str(wareki.parse("平成29年11月6日の週")), "2017-11-06")
        self.assertEqual(wareki.parse_year_month("野菜の生育状況及び価格見通し(令和元年5月)"), (2019, 5))


class Outlook(unittest.TestCase):
    def test_halves(self):
        r = maff_outlook.parse_judgement("<11月前半>平年並みで推移<11月後半>やや平年を上回って推移")
        self.assertEqual([(x["period"], x["level"]) for x in r], [("first_half", 0), ("second_half", 1)])

    def test_single(self):
        self.assertEqual(maff_outlook.parse_judgement("平年を下回って推移")[0]["level"], -2)
        self.assertEqual(maff_outlook.parse_judgement("〈4月前半〉平年を上回って推移〈4月後半〉平年並みで推移")[0]["level"], 2)


class Otoku(unittest.TestCase):
    HTML = ('<div id="main_content"><h1>今週のお手頃野菜(令和8年11月6日更新)</h1>今週は トマト<img>、たまねぎ<img> '
            'が大変お買い得となっております ！ にんじん<img>、ねぎ<img> ブロッコリー<img>、ばれいしょ<img> '
            'も平年を下回る価格となっております！ (単位：円/kg)</div>')

    def test_parse(self):
        r = maff_otoku.parse(self.HTML)
        self.assertEqual(r["date"], "2026-11-06")
        self.assertEqual(r["best"], ["tomato", "onion"])
        self.assertEqual(r["good"], ["carrot", "negi", "broccoli", "potato"])


class Seasonal(unittest.TestCase):
    def test_inflation_removed(self):
        # 毎年 10% ずつ上がるが、形は同じ（2 月が安い）→ 指数は年によらない
        monthly = {}
        for y in range(2015, 2020):
            for m in range(1, 13):
                monthly[(y, m)] = 100 * 1.1 ** (y - 2015) * (0.8 if m == 2 else 1.0)
        r = seasonal.index(monthly)
        self.assertEqual(r["cheap_months"], [2])
        self.assertEqual(r["n_years"], 5)
        self.assertAlmostEqual(r["index"][1] / r["index"][0], 0.8, places=2)

    def test_sparse_years_dropped(self):
        monthly = {(2020, m): 100 for m in range(1, 6)}  # 5 か月しかない
        self.assertIsNone(seasonal.index(monthly))


class Estat(unittest.TestCase):
    def test_values_and_series(self):
        vals = [
            {"@cat02": "01401", "@area": "13100", "@time": "2026000909", "$": "250"},
            {"@cat02": "01401", "@area": "13100", "@time": "2026000707", "$": "1,230"},
            {"@cat02": "01401", "@area": "13100", "@time": "2026000808", "$": "-"},
        ]
        d = estat.parse_values(vals)
        s = d["13100"]["01401"]
        self.assertEqual(s, {(2026, 9): 250, (2026, 7): 1230})
        j = estat.series_to_json(s)
        self.assertEqual(j, {"start": "2026-07", "values": [1230, None, 250]})
        self.assertEqual(estat.series_from_json(j), s)
        self.assertEqual(estat.time_code(2000, 1), "2000000101")

    def test_item_class(self):
        classes = {"tab": [1], "cat01": [{"code": "0020"}], "cat02": [{"code": "01401"}, {"code": "01402"}], "area": [1, 2, 3], "time": [1]}
        self.assertEqual(estat.item_class(classes), "cat02")


if __name__ == "__main__":
    unittest.main()
