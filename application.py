import os

from flask import Flask, session, render_template, request, redirect, jsonify
from flask_session import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
import requests

from helpers import login_required

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


@app.route("/", methods=["GET", "POST"])
@login_required
def index():
    if request.method=="POST":
        search = request.form.get("search")
        books = db.execute("SELECT * FROM books WHERE LOWER(isbn) LIKE LOWER(:search) OR LOWER(title) LIKE LOWER(:search) OR LOWER(author) LIKE LOWER(:search)", {"search": '%' + search + '%'}).fetchall()
        if len(books)>0:
            return render_template("index.html", books=books, message="Below are the books we found:")
    return render_template("index.html", books=[], message="No relevant book found.")

@app.route("/login", methods=["GET", "POST"])
def login():
    # forget any user id:
    session.clear()

    if request.method=="POST":
        # ensure username was submitted:
        if not request.form.get("username"):
            return render_template("error.html", message="Please enter your username")
        elif not request.form.get("password"):
            return render_template("error.html", message="Please enter your password")
        
        # search for the username:
        result = db.execute("SELECT * FROM users WHERE username=:username", {"username": request.form.get("username")}).fetchone()

        if len(result) == 0 or not check_password_hash(result[2], request.form.get("password")):
            return render_template("error.html", message="Your have entered incorrect username/password")
        
        # remember which user has logged in:
        session["user_id"] = result[0]

        # redirect to homgepage:
        return redirect("/")

    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    session.clear()

    if request.method=="POST":
        if not request.form.get("username"):
            return render_template("error.html", message="Please enter your username")
        elif not request.form.get("password"):
            return render_template("error.html", message="Please enter your password")

        if request.form.get("password") != request.form.get("password2"):
            return render_template("error.html", message="Passwords do not match")
        
        if db.execute("SELECT * FROM users WHERE username=:username", {"username": request.form.get("username")}) !=None:
            return render_template("error.html", message="Username already exists")

        # hash password:
        hash = generate_password_hash(request.form.get("password"))
        
        # insert new user into table:
        db.execute("INSERT INTO users (username, password) VALUES(:username, :password)", {"username": request.form.get("username"), "password": hash})
        result = db.execute("SELECT * FROM users WHERE username=:username", {"username": request.form.get("username")}).fetchone()
        db.commit()
        # remember session:
        session["user_id"] = result[0]
        return redirect("/")
    else:
        return render_template("register.html")

@app.route("/logout")
def logout():
    """Log user out"""
    # Forget any user_id
    session.clear()
    # Redirect user to login form
    return redirect("/")

@app.route("/check")
def check():
    """Return true if username available, else false, in JSON format"""
    rows = db.execute("SELECT * FROM users WHERE username = :username", {"username": request.args.get("username")}).fetchall()
    if len(rows)!=0:
        return jsonify("false")
    else:
        return jsonify("true")

@app.route("/book/<int:book_id>", methods=["GET", "POST"])
@login_required
def book(book_id):
    book = db.execute("SELECT * FROM books WHERE id=:id", {"id": book_id}).first()
    res = requests.get("https://www.goodreads.com/book/review_counts.json", params={"key": "5M9fIVSIHbpYFFc9N1FA", "isbns": book.isbn})
    rating = res.json()['books'][0]
    if request.method=="POST":
        # query to see if there is already a review:
        review = db.execute("SELECT * FROM reviews WHERE user_id=:user_id AND book_id=:book_id", {"user_id": session['user_id'], "book_id": book.id}).fetchall()
        if len(review)>0:
            return render_template("book.html", book=book, rating=rating, message="You have already submitted a review before.")
        else:
            review_rating = request.form.get("score")
            review_text = request.form.get("review")
            db.execute("INSERT INTO reviews (user_id, book_id, rating, review) VALUES (:user_id, :book_id, :rating, :review)", {"user_id": session['user_id'], "book_id": book.id, "rating": review_rating, "review": review_text})
            db.commit()
            return render_template("book.html", book=book, rating=rating, message="Thank you for your review!")
    return render_template("book.html", book=book, rating=rating, message="")

@app.route("/api/<isbn>", methods=["GET"])
def api(isbn):
    book = db.execute("SELECT * FROM books WHERE isbn=:isbn", {"isbn": isbn}).first()
    if len(book)==0:
        return render_template("error.html", message="404: book not found")
    else:
        res = requests.get("https://www.goodreads.com/book/review_counts.json", params={"key": "5M9fIVSIHbpYFFc9N1FA", "isbns": book.isbn})
        rating = res.json()['books'][0]
        return jsonify({"title": book.title, "author": book.author, "year": book.year, "isbn": isbn, "review_count": rating["work_ratings_count"], "average_score": rating["average_rating"]})

