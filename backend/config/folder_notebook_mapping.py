# Folder → Notebook Mapping Configuration
# =========================================
# Điền Folder ID từ Google Drive vào cột bên trái
# Folder ID lấy từ URL: https://drive.google.com/drive/folders/<FOLDER_ID>
#
# Ví dụ: Nếu URL của folder là:
#   https://drive.google.com/drive/folders/1ABC123xyz
# Thì folder_id = "1ABC123xyz"

FOLDER_NOTEBOOK_MAPPING = {
    # =========================================================================
    # HUB - Governance
    # =========================================================================
    # Folder: 00_HUB_Governance
    "1Uazyl_c0Rzp-FhrI3QD5Kokg3aYQP2B2": "c109af87-e8b5-4b27-a65a-f202013728f2",  # ADG_Marketing_SSOT_Hub
    
    # =========================================================================
    # D2Com Team (Direct to Consumer)
    # =========================================================================
    # Folder: 01_Marketing_D2Com/House_ID_Development (gồm 5 subfolder)
    "1p0IOzfnapVKjsIJD1KTYFY6_QL7Epz80": "910d504c-c79c-45c2-beed-46ec3548ff1d",  # D2Com_House_ID_Development
    
    # Folder: 01_Marketing_D2Com/Community_Activation
    "1rQASsb32BPuLKEwUQTJM6MvISO1lff_S": "f380dd9e-a550-4447-94b7-05bebee14130",  # D2Com_Community_Activation
    
    # Folder: 01_Marketing_D2Com/Product_Marketing_Solar
    "1O0FoUTGvCFwxveEi0tFgBF0RdNRmoG4O": "2c5703b5-a861-47e0-b099-5e5d0f251a63",  # D2Com_Product_Marketing_Solar
    
    # Folder: 01_Marketing_D2Com/Product_Marketing_Home
    "1mJTnd-VRXnIdpQOJq182svepM44GKmyx": "112ec6d5-b177-433b-910c-10cefacb2a84",  # D2Com_Product_Marketing_Home
    
    # =========================================================================
    # B2B Team
    # =========================================================================
    # Folder: 02_Marketing_B2B/Key_Account_Marketing
    "1_PSramSoeGLumoxs6tvRMDs-qzRGcl9L": "37b1c9dc-a4c0-40f9-9738-a14c2f727346",  # B2B_Key_Account_Marketing
    
    # Folder: 02_Marketing_B2B/Industrial_Solution_Marketing
    "145lyD-U-0MsdNaex-HibKW7w6z2cCs2O": "ce4b2bb9-3e4d-4bbd-8db8-a5d86a865d3a",  # B2B_Industrial_Solution_Marketing
    
    # Folder: 02_Marketing_B2B/OEM_Export_Marketing
    "1JQvfm2wGxJpnLIcEmkCfQAzFrT-8bj3a": "c56e66df-585e-4026-8afd-09437fa5cdb6",  # B2B_OEM_Export_Marketing
    
    # Folder: 02_Marketing_B2B/Solar_EPC_Solution_Marketing
    "1w9E_2POODy_VLseDNPg4c5W8zXhMQMN1": "92060e0b-d832-4deb-bd31-ea2830e60788",  # B2B_Solar_EPC_Solution_Marketing
    
    # =========================================================================
    # S2B2C Team
    # =========================================================================
    # Folder: 03_Marketing_S2B2C/Product_Marketing_Door
    "11fDMkM9m-YncX_RfCJHsxhsoPaUzfpF5": "12fd291c-6f6f-402f-b5ea-f7abe48b2c98",  # S2B2C_Product_Marketing_Door
    
    # Folder: 03_Marketing_S2B2C/Research_Marketing_Operation
    "1N50szxGUMIZZk2sX2vwDZpU7-mIhHU2W": "1b4e2446-f8dd-4ff7-9103-ddffdcaa6ad3",  # S2B2C_Research_Marketing_Operation
    
    # =========================================================================
    # MARCOM Team
    # =========================================================================
    # Folder: 04_MARCOM/Performance_Marketing
    "1Q_H_mdOHs2io41kXKQD-J99BXIV9Xna4": "d337caa7-d83a-4840-b65c-85b23100f15f",  # MARCOM_Performance_Marketing
    
    # Folder: 04_MARCOM/3D_Graphic_Designer
    "1dG0PSVbUl0k_7ZgoZdWMzSFmIIuy_aAg": "37887d96-dee8-4928-aa48-6d86188ae707",  # MARCOM_3D_Graphic_Designer
    
    # Folder: 04_MARCOM/Trade_Marketing
    "1XJOqJVNZN5VU_liytkwnPNETwWWaOmcQ": "c913448c-44b0-4dad-952e-c406ab13ce48",  # MARCOM_Trade_Marketing
    
    # Folder: 04_MARCOM/Event_Communication_Copywriter
    "1dIQ6BgL8FAWWhgV3Saf3pJz0Y4BYlP95": "19b23115-2c0d-4643-8adc-491936d6a76e",  # MARCOM_Event_Communication_Copywriter
    
    # Folder: 04_MARCOM/Corporate_Brand_Copywriter
    "1lOfLUhQWJUZGoN8SDP-ttIPsgf5KQ083": "553000fd-6be6-46b1-8423-a84bad228b4e",  # MARCOM_Corporate_Brand_Copywriter
    
    # Folder: 04_MARCOM/Brand_CX_Communication
    "1IW-b7A-lopacdts6RRK5rRfVOjNEjJk5": "d7ed1b62-c59a-4ebc-b29c-af2a24285e68",  # MARCOM_Brand_CX_Communication
}


def get_notebook_for_folder(folder_id: str) -> str | None:
    """
    Tra cứu notebook ID tương ứng với folder ID.
    
    Args:
        folder_id: Google Drive folder ID
        
    Returns:
        NotebookLM notebook ID hoặc None nếu không tìm thấy
    """
    return FOLDER_NOTEBOOK_MAPPING.get(folder_id)


def get_all_folder_ids() -> list[str]:
    """Trả về danh sách tất cả folder IDs đã config"""
    return list(FOLDER_NOTEBOOK_MAPPING.keys())


def get_all_notebook_ids() -> list[str]:
    """Trả về danh sách tất cả notebook IDs"""
    return list(FOLDER_NOTEBOOK_MAPPING.values())
