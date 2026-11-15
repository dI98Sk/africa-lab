"""54 государства Африки (члены ООН) — единый справочник для всего проекта.

Ключ — ISO 3166-1 alpha-3: во всех трёх источниках сводим страны именно к нему,
потому что названия расходятся ("Congo, Dem. Rep." vs "Democratic Republic of the Congo").
"""

AFRICA_ISO3: dict[str, str] = {
    "DZA": "Algeria", "AGO": "Angola", "BEN": "Benin", "BWA": "Botswana",
    "BFA": "Burkina Faso", "BDI": "Burundi", "CPV": "Cabo Verde", "CMR": "Cameroon",
    "CAF": "Central African Republic", "TCD": "Chad", "COM": "Comoros",
    "COD": "DR Congo", "COG": "Republic of the Congo", "CIV": "Côte d'Ivoire",
    "DJI": "Djibouti", "EGY": "Egypt", "GNQ": "Equatorial Guinea", "ERI": "Eritrea",
    "SWZ": "Eswatini", "ETH": "Ethiopia", "GAB": "Gabon", "GMB": "Gambia",
    "GHA": "Ghana", "GIN": "Guinea", "GNB": "Guinea-Bissau", "KEN": "Kenya",
    "LSO": "Lesotho", "LBR": "Liberia", "LBY": "Libya", "MDG": "Madagascar",
    "MWI": "Malawi", "MLI": "Mali", "MRT": "Mauritania", "MUS": "Mauritius",
    "MAR": "Morocco", "MOZ": "Mozambique", "NAM": "Namibia", "NER": "Niger",
    "NGA": "Nigeria", "RWA": "Rwanda", "STP": "São Tomé and Príncipe",
    "SEN": "Senegal", "SYC": "Seychelles", "SLE": "Sierra Leone", "SOM": "Somalia",
    "ZAF": "South Africa", "SSD": "South Sudan", "SDN": "Sudan", "TZA": "Tanzania",
    "TGO": "Togo", "TUN": "Tunisia", "UGA": "Uganda", "ZMB": "Zambia",
    "ZWE": "Zimbabwe",
}

assert len(AFRICA_ISO3) == 54, len(AFRICA_ISO3)

YEARS = range(2000, 2022)  # 2000–2021 включительно: период AidData GCDF 3.0
