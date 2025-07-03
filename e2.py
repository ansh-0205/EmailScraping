import torch
from transformers import BertForTokenClassification, BertTokenizer
import pandas as pd
import time
from datetime import datetime, timedelta
import os
import json
import sys
import logging
from imap_tools import MailBox, AND
from config import email_accounts

def setup_logging():
    if os.path.exists('/app'):
        log_dir = '/app/logs'
        json_path = '/app/email_data.json'
    else:
        log_dir = './logs'
        json_path = './email_data.json'
    
    os.makedirs(log_dir, exist_ok=True)
    
    handlers = [logging.StreamHandler(sys.stdout)]
    
    try:
        handlers.append(logging.FileHandler(os.path.join(log_dir, 'email_scraper.log')))
    except Exception as e:
        print(f"Warning: Could not create log file: {e}")
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=handlers
    )
    
    return json_path

JSON_FILE_PATH = setup_logging()
logger = logging.getLogger(__name__)

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

try:
    logger.info("Loading Model")
    model = BertForTokenClassification.from_pretrained('Ansh0205/EmailScraping')
    tokenizer = BertTokenizer.from_pretrained('Ansh0205/EmailScraping')
    model.eval()
    logger.info("Model loaded successfully")
except Exception as e:
    logger.error(f"Error loading model: {str(e)}")
    sys.exit(1)

def predict_text(sentence):
    try:
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
            if i < len(word_level_predictions) and word_level_predictions[i] != 'O' and word_level_predictions[i]!='B-Port_of_Loading' and word_level_predictions[i]!='B-Port_of_Destination':
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
    except Exception as e:
        logger.error(f"Error in predict_text: {str(e)}")
        return "", "", "", "", "", "", "", "", "", ""

def save_dataframe_to_json(dataframe, email_user, mode='append'):
    filename = JSON_FILE_PATH 
    
    try:
        if mode == 'clear':
            if os.path.exists(filename):
                os.remove(filename)
            logger.info(f"Cleared JSON file for {email_user}")
            return
        
        if dataframe.empty:
            logger.info(f"No new emails for {email_user}")
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
            elif 'Date' in record:
                record['Date'] = str(record['Date'])
        
        all_data = existing_data + new_records
        
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        with open(filename, 'w') as f:
            json.dump(all_data, f, indent=2, default=str)
        
        logger.info(f"Appended {len(new_records)} emails to {filename} (Total: {len(all_data)} emails)")
        
    except Exception as e:
        logger.error(f"Error saving dataframe to JSON: {str(e)}")

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
        self.cycle_interval = timedelta(minutes=5)
        
        logger.info(f"Initialized processor for {self.user}")
        
    def check_for_cycle_reset(self):
        current_time = datetime.now()
        if current_time - self.last_cycle_time >= self.cycle_interval:
            logger.info(f"=== 5-minute cycle completed for {self.user} ===")
            logger.info(f"Clearing JSON and starting fresh cycle at {current_time}")
            
            save_dataframe_to_json(pd.DataFrame(), self.user, mode='clear')
            
            self.seen_uids.clear()
            self.last_seen_uid = 0
            self.last_cycle_time = current_time
            
            return True
        return False
    
    def process_emails(self):
        try:
            self.check_for_cycle_reset()
            
            df = pd.DataFrame(columns=['companyId', 'companyBranchId', 'financialYearId', 'clientId', 'id', 'Sender', 'Subject', 'Date', 'Remarks', 'Mode_Of_Transport',
                                       'Port_Of_Loading', 'Port_Of_Destination', 'Container_status', 'Weight', 'Weight_unit', 'Quantity', 'Package Type', 'Cargo Type', 'Size'])
            
            with MailBox(self.imap_url).login(self.user, self.password, 'INBOX') as mailbox:
                messages = list(mailbox.fetch(reverse=True, limit=20, mark_seen=True))
                
                new_emails_found = False
                for msg in messages:
                    if msg.uid not in self.seen_uids and int(msg.uid) > self.last_seen_uid:
                        new_emails_found = True
                        self.last_seen_uid = int(msg.uid)
                        
                        remarks = msg.text or ""
                        emailSubject = msg.subject or ""
                        emailFrom = msg.from_ or ""
                        enquiryDate = msg.date
                        
                        logger.info(f"=== NEW EMAIL for {self.user} ===")
                        logger.info(f"SENDER : {emailFrom}")
                        logger.info(f"SUBJECT: {emailSubject}")
                        logger.info(f"DATE : {enquiryDate}")
                        logger.info(f"REMARKS: {remarks}")
                        
                        mot, cs, podid, polid, wt, wt_unit, quantity, package, cargo_type, size = predict_text(remarks)                      
                        
                        if "AIRPORT" in remarks.upper() or "AIR" in remarks.upper():
                            mot = "Air"
                        elif "OCEAN" in remarks.upper() or "SEA" in remarks.upper() or "CONTAINER" in remarks.upper():
                            mot = "Sea"
                        elif "TRUCK" in remarks.upper() or "ROAD" in remarks.upper():
                            mot = "Road"
                            
                        logger.info(f"Extracted - MODE: {mot}, POL: {polid.strip()}, POD: {podid.strip()}")
                        
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
                                     'Port_Of_Loading': polid.strip(), 
                                     'Port_Of_Destination': podid.strip(),
                                     'Container_status': cs.strip(), 
                                     'Weight': wt, 
                                     'Weight_unit': wt_unit.strip(),
                                     'Quantity': quantity.strip(),
                                     'Package Type': package.strip(),
                                     'Cargo Type': cargo_type.strip(),
                                     'Size': size.strip()
                                     }]
                        
                        if new_data and len(new_data) > 0:
                            new_df = pd.DataFrame(new_data)
                            if not new_df.empty:
                                if df.empty:
                                    df = new_df.copy()
                                else:
                                    df = pd.concat([df, new_df], ignore_index=True)
                        
                        self.seen_uids.add(msg.uid)
                        mailbox.delete(msg.uid)
                
                if not df.empty:
                    save_dataframe_to_json(df, self.user, mode='append')
                elif not new_emails_found:
                    current_time = datetime.now()
                    time_remaining = self.cycle_interval - (current_time - self.last_cycle_time)
                    logger.info(f"No new emails for {self.user} (Next cycle in {time_remaining})")
                
        except Exception as e:
            logger.error(f"Error processing {self.user}: {str(e)}")

def main():
    logger.info("Starting continuous email processing for multiple accounts...")
    logger.info("Checking emails every 2 seconds, 5-minute cycles for each account")
    
    try:
        processors = [EmailAccountProcessor(account) for account in email_accounts]
        logger.info(f"Initialized {len(processors)} email processors")
        
        while True:
            logger.info(f"--- Checking all accounts at {datetime.now()} ---")
            
            for processor in processors:
                try:
                    processor.process_emails()
                except Exception as e:
                    logger.error(f"Error with processor for {processor.user}: {str(e)}")
            
            time.sleep(2)
            
    except KeyboardInterrupt:
        logger.info("Shutting down email processing...")
    except Exception as e:
        logger.error(f"Fatal error in main loop: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()