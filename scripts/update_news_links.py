import json

def update_links():
    with open('data/macro_theory.json', 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Các chỉ số đã làm, cần bỏ qua
    excluded_ids = {"CPIAUCSL", "CPILFESL", "PAYEMS", "UNRATE", "PPIFID"}

    updated_samples = []
    
    for category in data['categories']:
        # Bỏ qua category glossary vì không phải dữ liệu thực tế
        if category['id'] == 'glossary':
            continue
            
        for indicator in category['indicators']:
            if indicator['id'] in excluded_ids:
                continue
                
            link = ""
            # Logic phân bổ link dựa trên ID, tên hoặc primary_link
            
            # 1. BEA (GDP, PCE, Personal Income, v.v.)
            if indicator['id'] in ["GDPC1", "PCEPI", "PCEPILFE", "PI", "PCE", "CORPPROFITS", "TOTALSA", "BOPGSTB", "EXPGS", "IMPGS"]:
                link = "https://www.bea.gov/itables"
            
            # 2. Census (Retail Sales, Housing Starts, Durable Goods, v.v.)
            elif indicator['id'] in ["RSAFS", "HOUST", "PERMIT", "HSN1F", "NEWORDER", "DGORDER", "TTLCONS", "WHLSLRIMSA", "RETAILINV", "GOODSTRADE"]:
                link = "https://www.census.gov/economic-indicators/"
                
            # 3. BLS
            elif indicator['id'] == "JTSJOL":
                link = "https://www.bls.gov/charts/job-openings-and-labor-turnover/opening-hire-seperation-rates.htm"
            elif "bls.gov" in indicator.get('primary_link', ''):
                link = "https://www.bls.gov/charts/"
                
            # 4. Federal Reserve
            elif indicator['id'] == "INDPRO":
                link = "https://www.federalreserve.gov/releases/g17/current/default.htm"
            elif indicator['id'] == "DFF":
                link = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
            elif "federalreserve.gov/releases" in indicator.get('primary_link', ''):
                # Cho M2SL, Fed Balance Sheet, v.v.
                link = indicator.get('primary_link')
                
            # 5. Michigan Sentiment
            elif "sca.isr.umich.edu" in indicator.get('primary_link', '') or "MICH" in indicator['id'] or indicator['id'] == "UMCSENT":
                link = "https://data.sca.isr.umich.edu/charts.html"
                
            # 6. Consumer Confidence
            elif indicator['id'] in ["CSCICP03USM665S", "CETI"]:
                link = "https://www.conference-board.org/topics/consumer-confidence"
                
            # 7. ISM (Sản xuất, Dịch vụ)
            elif "ismworld.org" in indicator.get('primary_link', '') or "ISM" in indicator['id'] or indicator['id'] in ["NAPM", "NAPMNMI"]:
                link = "https://www.ismworld.org/supply-management-news-and-reports/reports-for-business/"
                
            # 8. Department of Labor (Jobless Claims)
            elif indicator['id'] in ["ICSA", "CCSA", "IC4WSA"]:
                link = "https://www.dol.gov/ui/data.pdf"
                
            # 9. Khác
            elif indicator['id'] == "CHALLENGER":
                link = "https://www.challengergray.com/tags/job-cuts/"
            elif indicator['id'] == "ADPMNUSNERNSA":
                link = "https://adpemploymentreport.com/"
            elif indicator['id'] == "EXHOSLUSM495S": # Existing Home Sales
                link = "https://www.nar.realtor/research-and-statistics/housing-statistics/existing-home-sales"
            elif indicator['id'] == "USSTHPI":
                link = "https://www.fhfa.gov/DataTools/Downloads/Pages/House-Price-Index.aspx"
            elif indicator['id'] == "CSCH20":
                link = "https://www.spglobal.com/spdji/en/index-family/indicators/sp-corelogic-case-shiller/"
            elif "mba.org" in indicator.get('primary_link', ''):
                link = "https://www.mba.org/news-and-research/research-and-economics/single-family-research/mortgage-bankers-weekly-applications-survey"
            elif "eia.gov" in indicator.get('primary_link', ''):
                link = indicator.get('primary_link')
            elif indicator['id'] in ["DGS10", "DGS2"]:
                link = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve"
                
            # Nếu chưa có rules specific nhưng có primary link, ta sẽ fallback vào primary link làm base release
            else:
                link = indicator.get('primary_link', indicator.get('link', ''))

            indicator['news_release_link'] = link
            
            # Lưu lại vài mẫu để check
            if len(updated_samples) < 10 and link:
                updated_samples.append((indicator['short_name'], link))

    with open('data/macro_theory.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print("Cập nhật thành công!")
    print("\nMột số ví dụ các chỉ số đã được gán link:")
    for name, l in updated_samples:
        print(f"- {name}: {l}")

if __name__ == "__main__":
    update_links()
