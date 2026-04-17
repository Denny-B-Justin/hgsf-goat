import streamlit as st
import pandas as pd
import plotly.express as px
from venn import venn  
import matplotlib.pyplot as plt
from PIL import Image
import base64
from io import BytesIO
from sqlalchemy import create_engine

def keyword_search(df, hierarchy_name, keywords):
    """
    Searches for keywords in specified columns of a DataFrame and adds a 'Keyword Found' column.

    Args:
        df: The pandas DataFrame to search.
        keywords: A set of keywords to search for.

    Returns:
        The DataFrame with an added 'Keyword Found' column.
    """

    # Split the keywords by commas and strip any surrounding whitespace
    keywords = [keyword.strip() for keyword in keywords.split(',')]

    # Ensure the columns exist in the DataFrame
    search_columns = ['Indicators', 'PriorActions', 'DLI_DLR', 'PROJ_OBJECTIVE_TEXT', 'Components']
    for col in search_columns:
        if col not in df.columns:
            raise ValueError(f"Column '{col}' is missing from the DataFrame.")

    def check_keywords(row):
        """Checks if any keywords appear in the specified columns of a row."""
        for col in search_columns:
            value = row[col]
            if isinstance(value, str) and any(keyword.lower() in value.lower() for keyword in keywords):
                return 'Yes'
        return 'No'

    # Apply the keyword search to each row
    df[hierarchy_name] = df.apply(check_keywords, axis=1)
    return df


# -------------------- Load the Data -------------------- #
# engine = create_engine('postgresql://postgres:getdatabasemirra@128.199.226.170:5432/goat')
df = pd.read_csv("data_files/full_data.csv")  # Replace with your actual data source, e.g., from a database query
hierarchy_df = pd.read_csv("data_files/hierarchy.csv")

# -------------------- Streamlit App Configuration -------------------- #
st.set_page_config(
    page_title="Governance Operations Analytics Tool",
    page_icon=":bar_chart:",
    layout="wide",
)

# -------------------- Load and Display Logo -------------------- #
logo = Image.open("data_files/Logo.png").convert("RGBA")
logo = logo.resize((100, 100))
buffered = BytesIO()
logo.save(buffered, format="PNG")
logo_base64 = base64.b64encode(buffered.getvalue()).decode()
st.markdown(
    f"""
    <div style='display: flex; align-items: center;'>
        <img src='data:image/png;base64,{logo_base64}' style='width:100px; margin-right: 10px;'>
        <h1 style='margin: 0;'>Governance Operations Analytics Tool (GoAT)</h1>
    </div>
    """,
    unsafe_allow_html=True,
)

# -------------------- Tab Navigation -------------------- #
tabs = st.tabs(["Dashboard", "Keywords", "About"])

# -------------------- About Tab -------------------- #
with tabs[2]:
    st.header("About")
    st.markdown(
        """
        <div style='font-family: Arial, sans-serif; font-size: 1rem; line-height: 1.6;'>
            <p>The <strong> Governance Operations Analytics Tool (GoAT) </strong> allows for targeted searches in core fields of the World Bank’s three operation types. These encompass Development Policy Operations (DPO), Investment Project Lending (IPL), and Program for Results (PfoR). Clusters of keywords can be mapped to a particular thematic cluster of terms, for example, focused on Public Investment Management (PIM), public asset management (PAM), or State-Owned Enterprises (SOEs). The identified operations can also be an asset for the level of climate co-benefits (CCBs). GoAT also allows users to modify their thematic cluster of terms and vary the document sections considered in searches (e.g., PDOs and/or indicators or prior actions in DPOs). 

<br/>The GoAT tool is being operated and maintained by the World Bank’s Global Community of Practice (CoP) for Public Infrastructure Investments and Asset Governance (PIIAG) (P179442). To the extent enabled by the World Bank’s public and internal data resources, the GoAT aims to provide a real-time view of the current state of Bank operations. These include Board Approved operations and upstream operations before Board approval (i.e., Concept and Appraisal). The GoAT initiative also progressively demonstrates how generative AI can be applied to a subset of relevant project information (e.g., all World Bank projects with a substantive focus on Public Asset Governance or a sub-type thereof).   

<br/>The GoAT tool provides interfaces for both general and more data science-oriented users. The public version of GoAT offers a user-friendly interface. The GoAT tool was developed to demonstrate the power of Web Applications and Interactive Development Interface (IDE) codebooks as applied to gleaning operational intelligence from public investment financing data. In line with the World Bank’s commitment to public investment financing transparency, the recent GoAT interfaces in Table 1 have focused on leveraging openly accessible data through the World Bank’s Data Catalogue, mainly as implemented by Application Programming Interfaces (APIs). Where specific data is not yey available via public APIs, and/or is for official use only, the GoAT interfaces are deployed for official/internal access only.
</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

# -------------------- Dashboard Tab -------------------- #
with tabs[0]:
    st.subheader("GoAT Dashboard")

    # Filters Section
    col1, col2 = st.columns([1, 3])
    with col1:
        # Lending Instrument Filter
        landing_instr = st.multiselect(
            "Select Lending Instrument",
            options=df["LNDNG_INSTR_LONG_NAME"].unique(),
            default=df["LNDNG_INSTR_LONG_NAME"].unique(),
            key="landing_instr",
        )

        # Region Filter
        region_options = df[df["LNDNG_INSTR_LONG_NAME"].isin(landing_instr)]["Region"].unique()
        region = st.multiselect(
            "Select Region",
            options=region_options,
            default=region_options if len(region_options) > 0 else [],
            key="region",
        )

        # Keywords Filter
        project_types = st.multiselect(
            "Filter by Keywords",
            options=hierarchy_df["Hierarchy Name"].unique(),
            default=[],
            key="project_types",
        )
        
        # AND/OR Filter
        and_or_filter = st.radio(
            "Select filter type for Keywords",
            options=["AND", "OR"],
            index=0,
            key="and_or_filter",
        )

    # Apply Filters and Display Metrics
    with col2:
        if not region:
            filtered_df = pd.DataFrame()
        else:
            filtered_df = df[
                df["LNDNG_INSTR_LONG_NAME"].isin(landing_instr)
                & df["Region"].isin(region)
            ]

        if project_types:
            if and_or_filter == "AND":
                for project_type in project_types:
                    filtered_df = filtered_df[filtered_df[project_type] == "Yes"]
            elif and_or_filter == "OR":
                filtered_df = filtered_df[filtered_df[project_types].eq("Yes").any(axis=1)]

        total_projects = filtered_df.shape[0]
        st.metric(label="Total Number of Projects", value=total_projects)

        # Graph Tabs
        #graph_tabs = ["Project Status", "Lending Instrument", "Download Data", "Project View"]
        graph_tabs = ["Project Status", "Lending Instrument", "Download Data"]
        if 2 <= len(project_types) <= 4:
            graph_tabs.append("Keyword Search Venn")

        graph_tabs = st.tabs(graph_tabs)

        # Project Status Tab
        with graph_tabs[0]:
            if not filtered_df.empty:
                grouped_df1 = filtered_df.groupby(['PROJ_APPRVL_FY', 'PROJ_STAT_NAME'])['PROJ_ID'].nunique().reset_index()
                grouped_df1.columns = ['Approval FY', 'Project Status', 'Number of Projects']
                fig1 = px.bar(grouped_df1, x='Approval FY', y='Number of Projects', color='Project Status', title='Project Status')
                st.plotly_chart(fig1, use_container_width=True)

        # Lending Instrument Tab
        with graph_tabs[1]:
            if not filtered_df.empty:
                grouped_df2 = filtered_df.groupby(['PROJ_APPRVL_FY', 'LNDNG_INSTR_LONG_NAME'])['PROJ_ID'].nunique().reset_index()
                grouped_df2.columns = ['Approval FY', 'Lending Instrument', 'Number of Projects']

                fig2 = px.bar(
                    grouped_df2,
                    x='Approval FY',
                    y='Number of Projects',
                    color='Lending Instrument',
                    title='Lending Instrument',
                )
                st.plotly_chart(fig2, use_container_width=True)

        # Download Data Tab
        with graph_tabs[2]:
            columns_to_display = list(df.columns[: df.columns.get_loc("DLI_DLR") + 1])
            st.write("### Download Projects")
            if filtered_df.empty:
                st.write("No project found.")
            else:
                st.dataframe(filtered_df[columns_to_display])

        # Venn Diagram Tab
        if 2 <= len(project_types) <= 4:
            with graph_tabs[3]:
                project_sets = {}
                for keyword in project_types:
                    project_sets[keyword] = set(df[df[keyword] == 'Yes']['PROJ_ID'])

                plt.figure(figsize=(1.5, 1.5))
                venn(project_sets)
                plt.legend(
                    labels=project_sets.keys(),
                    loc="upper center",
                    bbox_to_anchor=(0.5, 1.001),
                    frameon=True,
                    ncol=len(project_sets),
                    fontsize=10
                )
                plt.subplots_adjust(left=0.05, right=0.95, top=0.98, bottom=0.05)
                st.pyplot(plt)

# -------------------- Keywords Tab -------------------- #
with tabs[1]:
    keyword_tabs = st.tabs(["Available Hierarchies", "Add New Keywords", "Delete Hierarchy"])

    # Available Hierarchies Tab
    with keyword_tabs[0]:
        if not hierarchy_df.empty:
            sunburst_df = hierarchy_df.copy()
            sunburst_df['Keyword'] = sunburst_df['Keyword'].apply(lambda x: ' '.join([word.capitalize() for word in x.split()]))
            sunburst_df['Keyword'] = sunburst_df['Keyword'].apply(lambda x: x.replace(' ', '<br>'))

            fig_sunburst = px.sunburst(
                sunburst_df,
                path=['Hierarchy Name', 'Keyword'],
                values=None,
                width=800,
                height=600,
            )
            st.plotly_chart(fig_sunburst, use_container_width=False)

    # Add New Keywords Tab
    with keyword_tabs[1]:
        with st.form("add_keyword_form"):
            hierarchy_name = st.text_input("Enter Hierarchy Name (e.g., PIM)")
            full_name = st.text_input("Enter Full Name (e.g., Public Investment Management)")
            new_keywords = st.text_input("Enter Keywords (comma separated)")

            submitted = st.form_submit_button("Add Keyword")

            if submitted:
                if not hierarchy_name or not full_name or not new_keywords:
                    st.error("All fields are compulsory. Please fill in all fields.")
                else:
                    keywords_list = [kw.strip() for kw in new_keywords.split(",")]
                    new_data = pd.DataFrame({
                        'Hierarchy Name': [hierarchy_name] * len(keywords_list),
                        'Full Name': [full_name] * len(keywords_list),
                        'Keyword': keywords_list
                    })
                    hierarchy_df = pd.concat([hierarchy_df, new_data], ignore_index=True)
                    # hierarchy_df.to_sql('hierarchy', engine, if_exists='replace', index=False)

                    df_combined = keyword_search(df, hierarchy_name, new_keywords)
                    # df_combined.to_sql('projects', engine, if_exists='replace', index=False)
                    st.success(f"Keywords added successfully to hierarchy '{hierarchy_name}'.")
                    
                    # Refresh the app
                    st.rerun() 

    # Delete Hierarchy Tab
    with keyword_tabs[2]:
        hierarchy_to_delete = st.selectbox("Select a Hierarchy to Delete", hierarchy_df["Hierarchy Name"].unique())

        if st.button("Delete Hierarchy"):
            hierarchy_df = hierarchy_df[hierarchy_df["Hierarchy Name"] != hierarchy_to_delete]
            # hierarchy_df.to_sql('hierarchy', engine, if_exists='replace', index=False)
            st.success(f"Hierarchy '{hierarchy_to_delete}' deleted successfully.")
            # Refresh the app
            st.rerun() 

