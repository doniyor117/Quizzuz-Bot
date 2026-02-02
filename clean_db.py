import asyncio
from bot_services.firebase_service import db

async def delete_collection(coll_ref, batch_size=10):
    """Deletes all documents in a collection."""
    docs = coll_ref.limit(batch_size).stream()
    deleted = 0

    for doc in docs:
        print(f"Deleting doc: {doc.id} from {coll_ref.id}")
        doc.reference.delete()
        deleted += 1

    if deleted >= batch_size:
        return await delete_collection(coll_ref, batch_size)

async def clean_database():
    print("⚠️ STARTING DATABASE CLEANUP...")
    print("This will delete ALL users, sets, and folders.")
    confirm = input("Type 'yes' to confirm: ")
    
    if confirm.lower() != 'yes':
        print("Cancelled.")
        return

    # 1. Delete all Sets
    print("\n--- Deleting Sets ---")
    await delete_collection(db.collection('sets'))
    
    # 2. Delete all Folders (Books)
    print("\n--- Deleting Folders ---")
    await delete_collection(db.collection('folders'))
    
    # 3. Delete all Users
    print("\n--- Deleting Users ---")
    await delete_collection(db.collection('users'))

    print("\n✅ Database Cleaned! You can now start the bot fresh.")

if __name__ == "__main__":
    # Wrapper to run async function
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(clean_database())