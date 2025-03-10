import asyncio
import requests
import datetime
import time
from solana.rpc.types import TokenAccountOpts
from solders.pubkey import Pubkey
from solana.rpc.commitment import Commitment, Confirmed, Finalized
from solana.rpc.api import RPCException
from solana.rpc.api import Client, Keypair
from dexscreener import DexscreenerClient
from solana.rpc.async_api import AsyncClient
from solders.compute_budget import set_compute_unit_price,set_compute_unit_limit
from spl.token.instructions import create_associated_token_account, get_associated_token_address, close_account, \
    CloseAccountParams
from util.create_close_account import  fetch_pool_keys,  make_swap_instruction
from spl.token.client import Token
from spl.token.core import _TokenCore

from dotenv import dotenv_values
config = dotenv_values(".env")

async_solana_client= AsyncClient(config["RPC_HTTPS_URL"]) #Enter your API KEY in .env file

solana_client = Client(config["RPC_HTTPS_URL"])

LAMPORTS_PER_SOL = 1000000000
MAX_RETRIES = 5
RETRY_DELAY = 3

#You can use getTimeStamp With Print Statments to evaluate How fast your transactions are confirmed

def getTimestamp():
    while True:
        timeStampData = datetime.datetime.now()
        currentTimeStamp = "[" + timeStampData.strftime("%H:%M:%S.%f")[:-3] + "]"
        return currentTimeStamp


async def get_token_account(ctx,
                                owner: Pubkey.from_string,
                                mint: Pubkey.from_string):
        try:
            account_data = await ctx.get_token_accounts_by_owner(owner, TokenAccountOpts(mint))
            return account_data.value[0].pubkey, None
        except:
            swap_associated_token_address = get_associated_token_address(owner, mint)
            swap_token_account_Instructions = create_associated_token_account(owner, owner, mint)
            return swap_associated_token_address, swap_token_account_Instructions

class token:
    def __init__(self, mint, name, symbol, bondingCurve, associatedBCurve) -> None:
        self.mint = mint
        self.name = name
        self.symbol = symbol
        self.bondingCurve = bondingCurve
        self.associatedBCurve = associatedBCurve


url = "https://client-api-2-74b1891ee9f9.herokuapp.com/coins?offset=0&limit=3&sort=created_timestamp&order=DESC&includeNsfw=true"

r = requests.get(url = url)

data = r.json()

tokens = []

for coin in data:
    new_token = token(coin['mint'], coin['name'], coin['symbol'], coin['bonding_curve'], coin['associated_bonding_curve'])
    tokens.append(new_token)



async def buy(solana_client, TOKEN_TO_SWAP_BUY, payer, amount):

    retry_count = 0
    while retry_count < MAX_RETRIES:
        try:
            # token_symbol, SOl_Symbol = getSymbol(TOKEN_TO_SWAP_BUY)
            mint = Pubkey.from_string(TOKEN_TO_SWAP_BUY)
            pool_keys = fetch_pool_keys(str(mint))
            amount_in = int(amount * LAMPORTS_PER_SOL)
            accountProgramId = solana_client.get_account_info_json_parsed(mint)
            TOKEN_PROGRAM_ID = accountProgramId.value.owner

            balance_needed = Token.get_min_balance_rent_for_exempt_for_account(solana_client)
            swap_associated_token_address, swap_token_account_Instructions = await get_token_account(async_solana_client,payer.pubkey(),mint)
            WSOL_token_account, swap_tx, payer, Wsol_account_keyPair, opts, = _TokenCore._create_wrapped_native_account_args(
                TOKEN_PROGRAM_ID, payer.pubkey(), payer, amount_in,
                False, balance_needed, Commitment("confirmed"))

            instructions_swap = make_swap_instruction(amount_in,
                                                      WSOL_token_account,
                                                      swap_associated_token_address,
                                                      pool_keys,
                                                      mint,
                                                      solana_client,
                                                      payer)
            params = CloseAccountParams(account=WSOL_token_account, dest=payer.pubkey(), owner=payer.pubkey(),
                                        program_id=TOKEN_PROGRAM_ID)
            closeAcc = (close_account(params))
            if swap_token_account_Instructions != None:
                swap_tx.add(swap_token_account_Instructions)

            #compute unit price and comute unit limit gauge your gas fees more explanations on how to calculate in a future article

            swap_tx.add(instructions_swap,set_compute_unit_price(25_232),set_compute_unit_limit(200_337),closeAcc)
            txn = solana_client.send_transaction(swap_tx, payer,Wsol_account_keyPair)
            txid_string_sig = txn.value
            if txid_string_sig:
                print("Transaction sent")
                # print(f"Transaction Signature Waiting to be confirmed: https://solscan.io/tx/{txid_string_sig}")
                print("Waiting Confirmation")

            confirmation_resp = solana_client.confirm_transaction(
                txid_string_sig,
                commitment=Confirmed,
                sleep_seconds=0.5,
            )

            if confirmation_resp.value[0].err == None and str(
                    confirmation_resp.value[0].confirmation_status) == "TransactionConfirmationStatus.Confirmed":
                print("Transaction Confirmed")
                print(f"Transaction Signature: https://solscan.io/tx/{txid_string_sig}")

                return

            else:
                print("Transaction not confirmed")
                return False


        except asyncio.TimeoutError:
            print("Transaction confirmation timed out. Retrying...")
            retry_count += 1
            time.sleep(RETRY_DELAY)
        except RPCException as e:
            print(f"RPC Error: [{e.args[0]}]... Retrying...")
            retry_count += 1
            time.sleep(RETRY_DELAY)
        except Exception as e:
            if "block height exceeded" in str(e):
                print("Transaction has expired due to block height exceeded. Retrying...")
                retry_count += 1
                await asyncio.sleep(RETRY_DELAY)
            else:
                print(f"Unhandled exception: {e}. Retrying...")
                retry_count += 1
                await asyncio.sleep(RETRY_DELAY)
        # except Exception as e:
        #     print(f"Unhandled exception: {e}. Retrying...")
        #     retry_count = MAX_RETRIES
        #     return False

    print("Failed to confirm transaction after maximum retries.")
    return False



##
async def main():
    DexscreenerClient()
    for tokenn in tokens:
        print("name: "  + tokenn.name)
        print("mint: "  + tokenn.mint)
        print("curve: "  + tokenn.bondingCurve)
        print("associatedBonding: "  + tokenn.associatedBCurve)
        print("Buying" + tokenn.name)


asyncio.run(main())


