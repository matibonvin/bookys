import os
import requests

from flask import Flask, session, render_template, request, redirect, url_for, jsonify
from flask_session import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from werkzeug.security import check_password_hash, generate_password_hash
from xml.etree import ElementTree

app = Flask(__name__)

# Check for environment variable
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL is not set")

# Configure session to use filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Set up database
engine = create_engine(os.getenv("DATABASE_URL"))
db = scoped_session(sessionmaker(bind=engine))

def goodreads(books):
    
    d = dict()
    error=[]
    
    for book in books:
        res = requests.get("https://www.goodreads.com/book/isbn/", params={"isbn": book.isbn, "key":"gegTzZXsPCrmdkItpaXyUw"})
        tree = ElementTree.fromstring(res.content)
        query = requests.get("https://www.goodreads.com/book/review_counts.json", params={"isbns": book.isbn, "key":"gegTzZXsPCrmdkItpaXyUw"})
        
        try: 
            response = query.json()
            
        except ValueError:
            error.append(tuple(book))
            continue
        
        response = response['books'][0]
        
        d[book.isbn]= {'image_url': tree[1][8].text, 'small_image_url': tree[1][9].text,'description': tree[1][16].text, 'review':response }
        
    return d, error
    
   
@app.route("/")
def index():
    books = db.execute("SELECT * FROM books ORDER BY random() LIMIT 6").fetchall()
    
    d, error = goodreads(books)
    
    books = list(books)
    
    if len(error) != 0:
        for e in error:
            books.remove(e)

    return render_template("index.html", d=d, books=books,)
    
@app.route('/register', methods=["GET", "POST"])
def register():
    """ Register user """
    
    if request.method == "POST":
        
        # Ensure username was submitted
        if not request.form.get("username"):
            return "Must submit username"
            
        # Ensure password was submitted
        elif not request.form.get("password"):
            return "Must submit password"
            
        # Ensure password was confirmed
        elif not request.form.get("confirmation"):
            return "Must confirm password"
        
        # Ensure passwords coincide
        elif request.form.get("password") != request.form.get("confirmation"):
            return "Passwords don't coincide"
            
        
        # Ensure username is unique in the database
        if db.execute("SELECT * FROM users WHERE id = :username", {"username": request.form.get("username")}).rowcount == 1:
           return "username is taken"
        
        # Hash password 
        hash = generate_password_hash(request.form.get("password"))
        
        # Insert username into database
        db.execute("INSERT INTO users (id, hash) VALUES (:username, :hash)", {"username":request.form.get("username"), "hash":hash})
        db.commit()
        
        # Remember which user has registered
        session["user_id"]=request.form.get("username")
        
        # Redirect user to home page
        return redirect('/')
    
    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")
        

@app.route('/login', methods=["GET", "POST"])
def login():
    """ Log user in. """
    
    # Forget any user id
    session.clear()
    
    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        
        # Ensure username was submitted
        if not request.form.get("username"):
            return "Must submit a username"
        
        # Ensure password was submitted
        elif not request.form.get("password"):
            return "Must submit a password"
        
        # Query database for username
        users = db.execute("SELECT id, hash FROM users WHERE id= :username", {"username":request.form.get("username")}).fetchall()

        # Ensure username exists and password is correct
        if len(users) != 1 or not check_password_hash(users[0]['hash'], request.form.get("password")):
                return "Invalid Username or password"
        
        # Remember which user has logged in
        session['user_id'] = users[0]['id']
        
        # Return user to home page
        return redirect('/')
        
    else:
        return render_template("login.html")

@app.route("/logout")
def logout():
    """ Log user out """
    
    # Forget any user id
    session.clear()
    
    # Redirect user to login form
    return redirect('/')
    
    
@app.route("/book/<isbn>", methods=['GET', 'POST'])
def book(isbn):
    
    if request.method == "POST":
        
        if not request.form.get('userreview'):
            return 'Must submit a review'
            
        user = session['user_id']
        
        rating = request.form.get('rating')
        
        review = request.form.get('userreview')
        
        if db.execute("SELECT * FROM reviews WHERE user_id = :user_id AND isbn=:isbn", {"user_id":user, "isbn":isbn}).rowcount >= 1:
            return "You have already submitted a review for this book."
            
        db.execute("INSERT INTO reviews (isbn, user_id, review, rating) VALUES (:isbn, :user_id, :review, :rating)", {"isbn":isbn,"user_id":user, "review":review, "rating":rating})
        db.commit()
        
        return redirect("/book/" + isbn)
        
    else:
        
        # Make sure book exists.
        book = db.execute("SELECT * FROM books WHERE isbn = :isbn", {"isbn": isbn}).fetchone()
        if book is None:
            return "No such book."
        
        res = requests.get("https://www.goodreads.com/book/isbn/", params={"isbn": book.isbn, "key":"gegTzZXsPCrmdkItpaXyUw"})
        tree = ElementTree.fromstring(res.content)
      
        query = requests.get("https://www.goodreads.com/book/review_counts.json", params={"isbns": book.isbn, "key":"gegTzZXsPCrmdkItpaXyUw"})
        try:
            response = query.json()
            
        except ValueError:
            print("Error in response from GoodReads API")
        
        response = response['books'][0]
        
        d = dict()
        d[book.isbn]= {'image_url': tree[1][8].text, 'small_image_url': tree[1][9].text,'description': tree[1][16].text, 'review':response }
            
        # Get all reviews.
        reviews = db.execute("SELECT user_id, review, rating FROM reviews WHERE isbn = :isbn", {"isbn": isbn}).fetchall()
        
        return render_template("book.html", book=book, d=d, reviews=reviews)
    
@app.route("/search", methods=['GET'])
def search():
    """ Get book results """
    
    if not request.args.get("search"):
        return "Must search a Book or an Author or an Isbn"
        
    books = db.execute("SELECT * FROM books WHERE lower(author) LIKE lower(:search) OR lower(title) LIKE lower(:search) OR lower(isbn) LIKE lower(:search) LIMIT 9", {"search":"%" + request.args.get("search") + "%"})
    
    if books.rowcount == 0:
        return "Book or Author or ISBN not found."
        
    books = books.fetchall()
    
    d, error = goodreads(books)
    
    if len(error) != 0:
        for e in error:
            books.remove(e)
    
    return render_template("index.html", books=books, d=d)
    
@app.route("/api/<isbn>", methods=['GET'])
def api(isbn):
    """ Returns book details """
    
    book = db.execute("SELECT books.title, books.author, books.year, books.isbn, \
                    COUNT(reviews.id) as count, \
                    AVG(reviews.rating) as average_score \
                    FROM books \
                    INNER JOIN reviews \
                    ON books.isbn = reviews.isbn \
                    WHERE books.isbn = :isbn \
                    GROUP BY books.title, books.author, books.year, books.isbn",
                    {"isbn": isbn})

    if not book.rowcount == 1:
        return jsonify({"Error": "Book not found"}), 404
    
    book = book.fetchone()
    
    book = dict(book.items())
    
    book['average_score'] = float('%.2f'%(book['average_score']))

    return jsonify(book)