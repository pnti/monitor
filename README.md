### Prezentacja aplikacji

Prosta aplikacja służąca do wyświetlania zadań na stacjach uczniów.

Zadania odczytywane są z pliku tekstowego i wyświetlane po kolei, po zatwierdzeniu wykonania poprzedniego zadania przez nauczyciela.

Uczeń przed rozpoczęciem wykonywania zadań podaje swoje imię i nazwisko, dzięki czemu nauczyciel wie kto siedzi przy konkretnej stacji.

Panel nauczyciela chroniony jest hasłem.

Stan aplikacji zachowywany jest w pliku tekstowym, w związku z tym można kontynować wykonywanie zadań na następnej lekcji.

### Konfiguracja i uruchamianie

Aplikacja domyślnie dostępna jest przez loopback, 127.0.0.1 na porcie 5000.

Panel nauczyciela dostępny jest w podkatalogu teacher: `127.0.0.1:5000/teacher`

Aby udostępnić japlikację w sieci lokalnej w klasie, należy w pliku `app.py` wpisać adresy IP indywidualnych stacji.

Aplikację najlepiej uruchamiać za pomocą skryptów startowych, które automatycznie obsługuja zależności.
