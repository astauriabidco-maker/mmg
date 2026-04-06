import sqlite3
def run():
    conn = sqlite3.connect("atelier.db")
    c = conn.cursor()
    c.execute("DROP TABLE IF EXISTS stock_transactions")
    c.execute("DROP TABLE IF EXISTS stock_items")
    c.execute("DROP TABLE IF EXISTS product_variants")
    c.execute("DROP TABLE IF EXISTS products")
    conn.commit()
    conn.close()
    print("Anciennes tables de stock plates supprimées. Prêts pour la V3 !")
if __name__ == "__main__":
    run()
