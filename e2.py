import torch
from transformers import BertForTokenClassification, BertTokenizer
import pandas as pd
import time
from datetime import datetime, timedelta
import os
import json
from imap_tools import MailBox, AND
from config import email_accounts

ids_to_labels = {
    0: 'O',
    1: 'B-Mode_of_transport',
    2: 'B-Weight',
    3: 'B-Weight_unit',
    4: 'B-Quantity',
    5: 'B-Package',
    6: 'B-Port_of_Destination',
    7: 'I-Port_of_Destination',
    8: 'B-Cargo_Type',
    9: 'I-Port_of_Loading',
    10: 'B-Port_of_Loading',
    11: 'B-Container_status',
    12: 'B-Size'
    }

model = BertForTokenClassification.from_pretrained('./updated_saved_bert_model')
tokenizer = BertTokenizer.from_pretrained('./updated_saved_bert_model')
model.eval()

def predict_text(sentence):
    inputs = tokenizer(sentence, padding='max_length', truncation=True, max_length=128, return_tensors="pt")
    ids = inputs["input_ids"]
    mask = inputs["attention_mask"]
    outputs = model(ids, mask)
    logits = outputs[0]

    active_logits = logits.view(-1, model.num_labels)
    flattened_predictions = torch.argmax(active_logits, axis=1)

    tokens = tokenizer.convert_ids_to_tokens(ids.squeeze().tolist())
    token_predictions = [ids_to_labels[i] for i in flattened_predictions.cpu().numpy()]
    wp_preds = list(zip(tokens, token_predictions))

    word_level_predictions = []
    for pair in wp_preds:
        if (pair[0].startswith("##")) or (pair[0] in ['[CLS]', '[SEP]', '[PAD]']):
            continue
        else:
            word_level_predictions.append(pair[1])

    str_rep = " ".join([t[0] for t in wp_preds if t[0] not in ['[CLS]', '[SEP]', '[PAD]']]).replace(" ##", "")
    
    mot = ""
    cs = ""
    polid = ""
    podid = ""
    wt = ""
    wt_unit = ""
    quantity = ""
    package = ""
    cargo_type = ""
    size = ""
    
    for i in range(len(str_rep.split())):
        if word_level_predictions[i] != 'O' and word_level_predictions[i]!='B-Port_of_Loading' and word_level_predictions[i]!='B-Port_of_Destination':
            if word_level_predictions[i] == 'B-Mode_of_transport':
                mot = str_rep.split()[i]
                
            elif word_level_predictions[i] == 'B-Container_status':
                cs += str_rep.split()[i]+" "
                
            elif word_level_predictions[i] == 'I-Port_of_Destination':
                if str_rep.split()[i] != 'door' and str_rep.split()[i] != 'sea' :
                    podid += str_rep.split()[i]+" "
                
            elif word_level_predictions[i] == 'I-Port_of_Loading':
                polid += str_rep.split()[i]+" " 
            
            elif word_level_predictions[i] == 'B-Weight':
                wt += str_rep.split()[i]+""
                
            elif word_level_predictions[i] == 'B-Weight_unit':
                wt_unit += str_rep.split()[i]+" " 

            elif word_level_predictions[i] == 'B-Quantity':
                quantity += str_rep.split()[i]+" " 
            
            elif word_level_predictions[i] == 'B-Package':
                package += str_rep.split()[i]+" " 
            
            elif word_level_predictions[i] == 'B-Cargo_Type':
                cargo_type += str_rep.split()[i]+" "

            elif word_level_predictions[i] == 'B-Size':
                size += str_rep.split()[i]+" " 
            
            

            
    
    return mot, cs, podid, polid, wt, wt_unit, quantity, package, cargo_type, size



def save_dataframe_to_json(dataframe, email_user, mode='append'):
    email_name = email_user.split('@')[0]
    filename = f"email_data.json"
    
    if mode == 'clear':
        if os.path.exists(filename):
            os.remove(filename)
        print(f"Cleared JSON file for {email_user}")
        return
    
    if dataframe.empty:
        print(f"No new emails for {email_user}")
        return
    
    existing_data = []
    if os.path.exists(filename):
        try:
            with open(filename, 'r') as f:
                existing_data = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            existing_data = []
    
    new_records = dataframe.to_dict('records')
    
    for record in new_records:
        if 'Date' in record and hasattr(record['Date'], 'isoformat'):
            record['Date'] = record['Date'].isoformat()
    
    all_data = existing_data + new_records
    
    with open(filename, 'w') as f:
        json.dump(all_data, f, indent=2, default=str)
    
    print(f"Appended {len(new_records)} emails to {filename} (Total: {len(all_data)} emails)")

class EmailAccountProcessor:
    def __init__(self, account_config):
        self.companyId = account_config['companyId']
        self.companyBranchId = account_config['companyBranchId']
        self.financialYearId = account_config['financialYearId']
        self.clientId = account_config['clientId']
        self.id = account_config['id']
        self.user = account_config['user']
        self.password = account_config['password']
        self.imap_url = account_config['imap_url']

        self.seen_uids = set()
        self.last_seen_uid = 0
        self.last_cycle_time = datetime.now()
        self.cycle_interval = timedelta(minutes=2)
        
    def check_for_cycle_reset(self):
        current_time = datetime.now()
        if current_time - self.last_cycle_time >= self.cycle_interval:
            print(f"\n=== 10-minute cycle completed for {self.user} ===")
            print(f"Clearing JSON and starting fresh cycle at {current_time}")
            
            save_dataframe_to_json(pd.DataFrame(), self.user, mode='clear')
            
            self.seen_uids.clear()
            self.last_seen_uid = 0
            self.last_cycle_time = current_time
            
            return True
        return False
    
    def process_emails(self):
        self.check_for_cycle_reset()
        
        df = pd.DataFrame(columns=['companyId', 'companyBranchId', 'financialYearId', 'clientId', 'id', 'Sender', 'Subject', 'Date', 'Remarks', 'Mode_Of_Transport',
                                   'Port_Of_Loading', 'Port_Of_Destination', 'Container_status', 'Weight', 'Weight_unit', 'Quantity', 'Package Type', 'Cargo Type', 'Size'])
        
        try:
            with MailBox(self.imap_url).login(self.user, self.password, 'INBOX') as mailbox:
                messages = list(mailbox.fetch(reverse=True, limit=20, mark_seen=True))
                
                new_emails_found = False
                for msg in messages:
                    if msg.uid not in self.seen_uids and int(msg.uid) > self.last_seen_uid:
                        new_emails_found = True
                        self.last_seen_uid = int(msg.uid)
                        
                        remarks = msg.text
                        emailSubject = msg.subject
                        emailFrom = msg.from_
                        enquiryDate = msg.date
                        
                        print(f"\n=== NEW EMAIL for {self.user} ===")
                        print(f"SENDER : {emailFrom}")
                        print(f"SUBJECT: {emailSubject}")
                        print(f"DATE : {enquiryDate}")
                        print(f"REMARKS: {remarks}")
                        
                        mot, cs, podid, polid, wt, wt_unit, quantity, package, cargo_type, size = predict_text(remarks)                      
                        
                        if "AIRPORT" in remarks.upper() or "AIR" in remarks.upper():
                            mot = "Air"
                        elif "OCEAN" in remarks.upper() or "SEA" in remarks.upper() or "CONTAINER" in remarks.upper():
                            mot = "Sea"
                        elif "TRUCK" in remarks.upper() or "ROAD" in remarks.upper():
                            mot = "Road"
                            
                        print(f"MODE: {mot}")
                        print(f"PORT_OF_LOADING: {polid}")
                        print(f"PORT_OF_DESTINATION: {podid}")
                        print(f"CONTAINER_STATUS: {cs}")
                        print(f"WEIGHT: {wt}")
                        print(f"WEIGHT UNIT: {wt_unit}")
                        print(f"QUANTITY: {quantity}")
                        print(f"PACKAGE TYPE: {package}")
                        print(f"CARGO TYPE: {cargo_type}")
                        print(f"SIZE: {size}")
                        
                        new_data = [{
                                     'companyId': self.companyId,
                                     'companyBranchId': self.companyBranchId,
                                     'financialYearId': self.financialYearId, 
                                     'clientId': self.clientId, 
                                     'id': self.id,
                                     'Sender': emailFrom, 
                                     'Subject': emailSubject, 
                                     'Date': enquiryDate, 
                                     'Remarks': remarks, 
                                     'Mode_Of_Transport': mot, 
                                     'Port_Of_Loading': polid, 
                                     'Port_Of_Destination': podid,
                                     'Container_status': cs, 
                                     'Weight': wt, 
                                     'Weight_unit': wt_unit,
                                     'Quantity': quantity,
                                     'Package Type': package,
                                     'Cargo Type': cargo_type,
                                     'Size': size
                                     }]
                        
                        df = pd.concat([df, pd.DataFrame(new_data)], ignore_index=True)
                        self.seen_uids.add(msg.uid)
                        mailbox.delete(msg.uid)
                
                if not df.empty:
                    save_dataframe_to_json(df, self.user, mode='append')
                elif not new_emails_found:
                    current_time = datetime.now()
                    time_remaining = self.cycle_interval - (current_time - self.last_cycle_time)
                    print(f"No new emails for {self.user} (Next cycle in {time_remaining})")
                
        except Exception as e:
            print(f"Error processing {self.user}: {str(e)}")

def main():
    print("Starting continuous email processing for multiple accounts...")
    print("Checking emails every 5 seconds, 10-minute cycles for each account")
    
    processors = [EmailAccountProcessor(account) for account in email_accounts]
    
    while True:
        print(f"\n--- Checking all accounts at {datetime.now()} ---")
        
        for processor in processors:
            try:
                processor.process_emails()
            except Exception as e:
                print(f"Error with processor for {processor.user}: {str(e)}")
        
        time.sleep(2)

if __name__ == "__main__":
    main()