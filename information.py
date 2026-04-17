# All the columns:
# PROJ_ID, PROJ_DISPLAY_NAME, PROJ_APPRVL_FY, PROJ_DEV_OBJECTIVE_DESC, PROJ_STAT_NAME, CNTRY_SHORT_NAME, LNDNG_INSTR_LONG_NAME, 
# LEAD_GP_NAME, CMT_AMT, PROJ_OBJECTIVE_TEXT, Region, Climate Financing (%), Adaptation (%), Mitigation (%), PriorActions, 
# Indicators, Components, DLI_DLR

# All the columns:
# PROJ_ID                       - Project ID (Y)
# PROJ_DISPLAY_NAME             - Project Name (Y)
# PROJ_APPRVL_FY                - Approval Fiscal Year (Y, but in DDMMYYYY. Take only YYYY)
# PROJ_DEV_OBJECTIVE_DESC       - (N) Project Development Objective (Five sentences describing the project)
# PROJ_STAT_NAME                - Project Status (Y)
# CNTRY_SHORT_NAME              - Country Name (Y)
# LNDNG_INSTR_LONG_NAME         - Project Type (Y)
# LEAD_GP_NAME                  - (N) Lead Global Practice - Two to Four words describing the project (eg. Urban, Resilience and Land)
# CMT_AMT                       - (N) Commitment Amount
# PROJ_OBJECTIVE_TEXT           - Same as PROJ_DEV_OBJECTIVE_DESC (N)
# Region                        - Region (Y)
# Climate Financing (%)         - (N) Study the project details and find climate financing as a percentage of total project cost
# Adaptation (%)                - (N) Study the project details and find adaptation financing as a percentage of total project cost
# Mitigation (%)                - (N) Study the project details and find mitigation financing as a percentage of total project cost
# PriorActions                  - (N) If there is any prior actions about this project is mentioned in the file then write it with information including the date and description. If not available, write "Not Available"
# Indicators                    - (N) If there are any indicators, KPIs, IRIs, or any quantitative metrics mentioned in the file that are associated with the project, write them with information including the name of the indicator and its description. If not available, write "Not Available"
# Components                    - (N) All the components that are associated with the project. If not available, write "Not Available"
# DLI_DLR                       - (N) Disbursement Linked Indicators (DLI) and Disbursement Linked Results (DLR)

from document_conversion import convert_to_markdown
import os 

docs_folder = "docs"

for root, dirs, files in os.walk(docs_folder):
    for file in files:
        if file.endswith(".pdf"):
            pdf_path = os.path.join(root, file)
            print(pdf_path)
            convert_to_markdown(
                filepath= pdf_path,
                output_dir = 'markdown',
                )
            # print(pdf_path)

