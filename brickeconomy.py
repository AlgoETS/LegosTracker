import csv
from pydantic import BaseModel
from typing import Dict, List, Optional
from playwright.async_api import async_playwright
import asyncio
import json
import re
from datetime import datetime

class SetDetails(BaseModel):
    name: str
    value: str

class HistoryEntry(BaseModel):
    date: datetime
    number: float
    tooltip: Optional[str]
    annotation: Optional[str]
    annotationText: Optional[str]

class NewEntry(BaseModel):
    date: datetime
    value1: float
    value2: float
    value3: float
    value4: float
    description: Optional[str] = None


class LegoSet(BaseModel):
    details: List[SetDetails]
    pricing: List[SetDetails]
    quick_buy: List[SetDetails]
    set_predictions: List[SetDetails]
    set_facts: str
    subtheme_analysis: List[SetDetails]


class LegoAPI:
    root_url = "https://www.brickeconomy.com"

    def __init__(self, set_list):
        self.set_list = set_list
        self.output_file = "lego_sets.csv"

    async def start(self):
        try:
            with open(self.set_list, "r") as f:
                set_list = [line.rstrip() for line in f.readlines()]
        except Exception as e:
            print("Error opening input file")
            raise e

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)  # Set headless to False
            page = await browser.new_page()

            for set_num in set_list:
                search_url = f"{self.root_url}/search?query={set_num}"
                await page.wait_for_load_state("load")
                await page.goto(search_url)

                try:
                    possible_links = await page.query_selector_all(
                        "#ContentPlaceHolder1_ctlSetsOverview_GridViewSets > tbody > tr:nth-child(2) > td.ctlsets-left > div.mb-5 > h4 > a"
                    )
                except Exception as e:
                    raise ValueError(f"Error parsing HTML: {e}")

                if not possible_links:
                    raise ValueError(f"No links found for set number: {set_num}")

                for link in possible_links:
                    href = await link.get_attribute("href")
                    print(href)
                    test_num = href.split("/")[2].split("-")[0]
                    print(test_num)
                    if str(test_num) in str(set_num):
                        set_details = href.split("/")[2:4]
                        await page.goto(self.root_url + href)
                        await page.wait_for_load_state("load")
                        await self.parse_history(page, set_num)
                        await self.parse_set(page, set_details)

            await browser.close()

    async def parse_history(self, page, set_num):
        try:
            script_tags = await page.query_selector_all("script")
            desired_script_content = None

            for script_tag in script_tags:
                script_content = await script_tag.inner_text()
                if "data.addRows([" in script_content:
                    desired_script_content = script_content
                    break

            if desired_script_content:
                pattern = r"data\.addRows\((\[.*?\]\));"
                matches = re.findall(pattern, desired_script_content, re.DOTALL)
                if matches:
                    history_data = matches[0].replace("\n", "").replace("null", "'null'")

                    history_entries = []
                    pattern_date = re.compile(r"new Date\((\d+), (\d+), (\d+)\), (\d+\.?\d*), '([^']*)', '([^']*)'(?:, '([^']*)')?(?:, '([^']*)')?")

                    for match in pattern_date.finditer(history_data):
                        year, month, day = map(int, match.groups()[:3])
                        month += 1
                        date = datetime(year, month, day)
                        value = match.group(4)
                        currency_value = match.group(5)
                        status = match.group(6) if match.group(6) else None
                        description = match.group(7) if match.group(7) else None
                        history_entries.append(
                            HistoryEntry(
                                date=date,
                                number=value,
                                tooltip=currency_value,
                                annotation=status,
                                annotationText=description,
                            )
                        )

                    # Write to CSV
                    with open(f"{set_num}_history.csv", mode="w", newline="", encoding="utf-8") as file:
                        writer = csv.writer(file)
                        writer.writerow(
                            ["Date", "Value", "Currency Value", "Status", "Description"]
                        )
                        for entry in history_entries:
                            writer.writerow(
                                [
                                    entry.date,
                                    entry.number,
                                    entry.tooltip,
                                    entry.annotation,
                                    entry.annotationText,
                                ]
                            )

                    print("History data written to CSV")
                    print(len(matches))
                    if len(matches) > 1:
                        new_data = matches[1].replace("\n", "").replace("null", "'null'")
                        pattern_new = re.compile(r"new Date\((\d+), (\d+), (\d+)\), (\d+\.?\d*), (\d+\.?\d*), (\d+\.?\d*), (\d+\.?\d*), '([^']*)'")
                        new_entries = []

                        for match in pattern_new.finditer(new_data):
                            year, month, day = map(int, match.groups()[:3])
                            month += 1
                            date = datetime(year, month, day)
                            value1, value2, value3, value4 = map(float, match.groups()[3:7])
                            description = match.group(8)
                            new_entries.append(
                                NewEntry(
                                    date=date,
                                    value1=value1,
                                    value2=value2,
                                    value3=value3,
                                    value4=value4,
                                    description=description,
                                )
                            )

                        # Write to CSV
                        with open(f"{set_num}_new.csv", mode="w", newline="", encoding="utf-8") as file:
                            writer = csv.writer(file)
                            writer.writerow(
                                ["Date", "Value 1", "Value 2", "Value 3", "Value 4", "Description"]
                            )
                            for entry in new_entries:
                                writer.writerow(
                                    [
                                        entry.date,
                                        entry.value1,
                                        entry.value2,
                                        entry.value3,
                                        entry.value4,
                                        entry.description,
                                    ]
                                )
                        print("New data written to CSV")
                    else:
                        pass

                else:
                    print("Could not find 'data.addRows([...]);' in the script content.")
            else:
                print("Script tag with 'data.addRows([' not found.")
        except Exception as e:
            print(f"An error occurred while extracting data: {e}")

    async def parse_set(self, page, set_details):
        # Set Details
        set_details_div = await page.query_selector(
            "div#ContentPlaceHolder1_SetDetails"
        )
        set_details_rows = await set_details_div.query_selector_all(".row.rowlist")

        set_info = []
        for row in set_details_rows:
            key_element = await row.query_selector(".text-muted")
            value_element = await row.query_selector(".col-xs-7")
            if key_element and value_element:
                key = await key_element.inner_text()
                value = await value_element.inner_text()
                set_info.append(SetDetails(name=key.strip(), value=value.strip()))

        # Set Pricing
        set_pricing_div = await page.query_selector(
            "div#ContentPlaceHolder1_PanelSetPricing"
        )
        pricing_rows = await set_pricing_div.query_selector_all(".row.rowlist")

        pricing_info = []
        for row in pricing_rows:
            key_element = await row.query_selector(".text-muted")
            value_element = await row.query_selector(".col-xs-7")
            if key_element and value_element:
                key = await key_element.inner_text()
                value = await value_element.inner_text()
                pricing_info.append(SetDetails(name=key.strip(), value=value.strip()))

        # Quick Buy
        quick_buy_div = await page.query_selector(
            "div#ContentPlaceHolder1_PanelSetBuying"
        )
        quick_buy_rows = await quick_buy_div.query_selector_all(".row.rowlist")

        quick_buy_info = []
        for row in quick_buy_rows:
            key_element = await row.query_selector(".text-muted")
            value_element = await row.query_selector(".col-xs-7")
            if key_element and value_element:
                key = await key_element.inner_text()
                value = await value_element.inner_text()
                quick_buy_info.append(SetDetails(name=key.strip(), value=value.strip()))

        # Set Predictions
        set_predictions_div = await page.query_selector(
            "div#ContentPlaceHolder1_PanelSetPredictions"
        )
        set_predictions_rows = await set_predictions_div.query_selector_all(
            ".row.rowlist"
        )

        set_predictions_info = []
        for row in set_predictions_rows:
            key_element = await row.query_selector(".text-muted")
            value_element = await row.query_selector(".col-xs-7")
            if key_element and value_element:
                key = await key_element.inner_text()
                value = await value_element.inner_text()
                set_predictions_info.append(
                    SetDetails(name=key.strip(), value=value.strip())
                )

        # Set Facts
        set_facts_div = await page.query_selector(
            "div#ContentPlaceHolder1_PanelSetFacts"
        )
        if set_facts_div:
            set_facts = await set_facts_div.inner_text()
            set_facts = set_facts.strip()
        else:
            set_facts = "No set facts available"

        # Subtheme Analysis
        subtheme_analysis_div = await page.query_selector(
            "div#ContentPlaceHolder1_PanelSetAnalysis"
        )
        subtheme_analysis_rows = await subtheme_analysis_div.query_selector_all(
            ".row.rowlist"
        )

        subtheme_analysis_info = []
        for row in subtheme_analysis_rows:
            key_element = await row.query_selector(".text-muted")
            value_element = await row.query_selector(".col-xs-7")
            if key_element and value_element:
                key = await key_element.inner_text()
                value = await value_element.inner_text()
                subtheme_analysis_info.append(
                    SetDetails(name=key.strip(), value=value.strip())
                )

        # Create LegoSet object
        lego_set = LegoSet(
            details=set_info,
            pricing=pricing_info,
            quick_buy=quick_buy_info,
            set_predictions=set_predictions_info,
            set_facts=set_facts,
            subtheme_analysis=subtheme_analysis_info,
        )

        # Write to CSV
        await self.write_to_csv(lego_set)

    async def write_to_csv(self, lego_set):
        with open(self.output_file, mode="a", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)

            # Write the headers
            writer.writerow(
                [
                    "Details",
                    "Pricing",
                    "Quick Buy",
                    "Set Predictions",
                    "Set Facts",
                    "Subtheme Analysis",
                ]
            )

            # Find the maximum length among all sections
            max_length = max(
                len(lego_set.details),
                len(lego_set.pricing),
                len(lego_set.quick_buy),
                len(lego_set.set_predictions),
                len(lego_set.subtheme_analysis),
            )

            # Write data row by row
            for i in range(max_length):
                row = [
                    lego_set.details[i].value if i < len(lego_set.details) else "",
                    lego_set.pricing[i].value if i < len(lego_set.pricing) else "",
                    lego_set.quick_buy[i].value if i < len(lego_set.quick_buy) else "",
                    (
                        lego_set.set_predictions[i].value
                        if i < len(lego_set.set_predictions)
                        else ""
                    ),
                    lego_set.set_facts if i == 0 else "",  # Write set facts only once
                    (
                        lego_set.subtheme_analysis[i].value
                        if i < len(lego_set.subtheme_analysis)
                        else ""
                    ),
                ]
                writer.writerow(row)


# Usage
async def main():
    # Clear existing content of the CSV file
    with open("lego_sets.csv", mode="w", newline="", encoding="utf-8") as file:
        pass

    lego_api = LegoAPI("set_list.txt")
    await lego_api.start()


asyncio.run(main())
